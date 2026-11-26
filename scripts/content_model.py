"""Content model: load, validate and gate the data objects in content/.

Every object is a JSON file with a `_meta` block. Facts and copy carry a `status`:
draft | approved | verified | missing .
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"

STATUSES = {"draft", "approved", "verified", "missing"}
BLOCKING = {"draft", "missing"}

# Fields that must be present and non-empty in every build (by object root name).
REQUIRED = {
    "site": ["url", "name", "language", "locale", "title", "description", "nav", "ctas", "audience"],
    "person": ["id", "name", "brandName", "descriptors", "bio"],
    "faq": ["items"],
    "sections/01-hero": ["id", "number", "h1", "identities", "statement", "ctas"],
    "sections/02-about": ["id", "number", "heading", "profiles"],
    "sections/03-bring": ["id", "number", "heading", "offerings"],
    "sections/04-standing": ["id", "number", "heading", "bioRef", "timeline"],
    "sections/05-building": ["id", "number", "heading", "product", "stages"],
    "sections/06-exploring": ["id", "number", "heading", "projects"],
    "sections/07-writing": ["id", "number", "heading", "featured", "articles"],
    "sections/08-contact": ["id", "number", "heading", "headline", "forms"],
}


class ContentError(Exception):
    """A content object breaks a rule. Messages read `file → json.path: problem`."""


class Content:
    def __init__(self, root=CONTENT):
        self.root = Path(root)
        self.objects = {}   # name -> data   (name: "site", "person", "sections/01-hero", ...)
        self.files = {}     # name -> Path
        for path in sorted(self.root.rglob("*.json")):
            name = path.relative_to(self.root).with_suffix("").as_posix()
            try:
                self.objects[name] = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                raise ContentError(f"{self.rel(path)}: invalid JSON ({e})")
            self.files[name] = path

    # ------------------------------------------------------------- accessors
    def rel(self, path):
        path = Path(path)
        return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)

    def __getitem__(self, name):
        return self.objects[name]

    @property
    def site(self):
        return self.objects["site"]

    @property
    def person(self):
        return self.objects["person"]

    def sections(self):
        """Homepage sections in order (content/sections/NN-name.json)."""
        return [self.objects[n] for n in sorted(self.objects) if n.startswith("sections/")]

    # ----------------------------------------------------------- references
    def resolve(self, ref):
        """Resolve 'person.bio.professional', 'sections/03-bring.offerings[business]',
        'person.affiliations[2]', 'person.sameAs[LinkedIn]'. Raises KeyError."""
        ref = ref.strip()
        root = max((n for n in self.objects if ref == n or ref.startswith(n + ".") or ref.startswith(n + "[")),
                   key=len, default=None)
        if root is None:
            raise KeyError(f"no object named in '{ref}'")
        node = self.objects[root]
        for key, index in re.findall(r"\.?([A-Za-z_][\w-]*)|\[([^\]]+)\]", ref[len(root):]):
            if key:
                if not isinstance(node, dict) or key not in node:
                    raise KeyError(f"'{key}' not found in '{ref}'")
                node = node[key]
            else:
                if not isinstance(node, list):
                    raise KeyError(f"[{index}] applied to a non-list in '{ref}'")
                if index.isdigit():
                    if int(index) >= len(node):
                        raise KeyError(f"index {index} out of range in '{ref}'")
                    node = node[int(index)]
                else:
                    hits = [x for x in node if isinstance(x, dict)
                            and index in (x.get("id"), x.get("label"), x.get("name"))]
                    if not hits:
                        raise KeyError(f"no item '{index}' in '{ref}'")
                    node = hits[0]
        return node

    # ------------------------------------------------------------ validation
    def validate(self):
        """Structural checks that apply to every build. Returns a list of error strings."""
        errors = []
        for name, data in self.objects.items():
            where = self.rel(self.files[name])
            if not isinstance(data, dict) or "_meta" not in data:
                errors.append(f"{where}: missing `_meta` block")
                continue
            status = data["_meta"].get("status")
            if status not in STATUSES:
                errors.append(f"{where} → _meta.status: '{status}' is not one of {sorted(STATUSES)}")
            for field in REQUIRED.get(name, []):
                if data.get(field) in (None, "", [], {}):
                    errors.append(f"{where} → {field}: required")
            if name == "evidence":  # lists may be empty until Brandon adds evidence, but must exist
                for field in ("events", "publications", "certifications", "recognitions", "baContributions"):
                    if not isinstance(data.get(field), list):
                        errors.append(f"{where} → {field}: must be a list")
            for path, value in walk(data):
                if path.startswith(("_meta", "schemas")) or "Schema" in path:
                    continue  # documentation of shapes, not data
                key = path.rsplit(".", 1)[-1]
                if key == "status" and value is not None and value not in STATUSES:
                    errors.append(f"{where} → {path}: '{value}' is not one of {sorted(STATUSES)}")
                if isinstance(value, str) and (key.endswith("Ref") or key == "ref"):
                    for ref in value.split(","):
                        errors += self._check_ref(where, path, ref)
                if key in ("sources", "links") and isinstance(value, list):
                    for ref in value:
                        if isinstance(ref, str) and not ref.startswith(("http", "/")):
                            errors += self._check_ref(where, path, ref)
        return errors

    def _check_ref(self, where, path, ref):
        try:
            self.resolve(ref)
            return []
        except KeyError as e:
            return [f"{where} → {path}: unresolved reference '{ref.strip()}' ({e.args[0]})"]

    # ---------------------------------------------------------- release gate
    def release_problems(self):
        """Everything that blocks a release build. Returns a list of strings."""
        problems = []
        for name, data in self.objects.items():
            where = self.rel(self.files[name])
            if data.get("_meta", {}).get("status") in BLOCKING:
                problems.append(f"{where} → _meta.status: '{data['_meta']['status']}' (needs approved/verified)")
            for path, value in walk(data):
                if path.startswith("_meta") or path.startswith("schemas") or path.endswith("Schema"):
                    continue
                key = path.rsplit(".", 1)[-1]
                if key == "status" and value in BLOCKING:
                    problems.append(f"{where} → {path}: '{value}'")
            for path, obj in walk_dicts(data):
                if path.startswith("_meta") or path.startswith("schemas"):
                    continue
                # A null value with a pending note means the fact is still owed.
                for key, val in obj.items():
                    if val is None and f"{key}Note" in obj:
                        problems.append(f"{where} → {join(path, key)}: null with pending note")
                # Statistics need verified status and evidence .
                if {"value", "label"} <= obj.keys() and "evidenceRef" in obj:
                    if obj.get("status") != "verified":
                        problems.append(f"{where} → {path}: statistic must be 'verified'")
                    if "definition" in obj and not obj["definition"]:
                        problems.append(f"{where} → {path}.definition: statistic needs a visible definition")
        return problems


# ----------------------------------------------------------------- tree walks

def join(path, key):
    return f"{path}.{key}" if path else str(key)


def walk(node, path=""):
    """Yield (json.path, value) for every scalar/list leaf and every key."""
    if isinstance(node, dict):
        for k, v in node.items():
            p = join(path, k)
            yield p, v
            if isinstance(v, (dict, list)):
                yield from walk(v, p)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            p = f"{path}[{i}]"
            if isinstance(v, (dict, list)):
                yield from walk(v, p)
            else:
                yield p, v


def walk_dicts(node, path=""):
    """Yield (json.path, dict) for every dict in the tree, including the root."""
    if isinstance(node, dict):
        yield path, node
        for k, v in node.items():
            yield from walk_dicts(v, join(path, k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk_dicts(v, f"{path}[{i}]")


def stat_problems(content):
    """ displayed speaking stats must not exceed what verified evidence supports."""
    events = [e for e in content["evidence"].get("events", []) if e.get("status") == "verified"]
    computed = {
        "events-count": len(events),
        "attendee-reach": sum(int(e.get("attendance") or 0) for e in events),
        "countries": len({e["country"] for e in events if e.get("country")}),
    }
    problems = []
    for offering in content["sections/03-bring"].get("offerings", []):
        for st in offering.get("stats", []):
            if st.get("id") not in computed:
                continue
            shown = int(re.sub(r"[^\d]", "", str(st.get("value", ""))) or 0)
            if shown > computed[st["id"]]:
                problems.append(f"content/sections/03-bring.json → stat '{st['id']}' shows {st['value']} but "
                                f"verified events in content/evidence.json support {computed[st['id']]:,}")
    return problems
