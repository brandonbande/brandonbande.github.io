// Get the element where you want to display the typing effect
var element = document.getElementById("role");

// Define the text you want to type
var roleText = [
  "I am a developer",
  "I am a designer",
  "I am a community lead"
];

// Define the speed of typing in milliseconds
var speed = 200;

// Initialize a variable to store the current index of the character being typed
var index = 0;

// Initialize a variable to store the current index of the role being typed
var roleIndex = 0;

// Define a function that will type one character at a time
function type() {
  // Check if the index is less than the length of the current role
  if (index < roleText[roleIndex].length) {
    // Append the current character and a span element with a blinking cursor style to the element's innerHTML
    element.innerHTML =
      roleText[roleIndex].slice(0, index + 1) +
      '<span style="border-right: 0.08em solid; animation: blink 0.75s step-end infinite;"> </span>';
    // Increment the index
    index++;
    // Call the type function again after a delay
    setTimeout(type, speed);
  } else {
    // Clear the element's innerHTML
    element.innerHTML = "";
    // Reset the index
    index = 0;
    // Increment the roleIndex and wrap it around if it reaches the end of the roleText array
    roleIndex = (roleIndex + 1) % roleText.length;
    // Call the type function again after a delay
    setTimeout(type, speed);
  }
}

// Call the type function for the first time
type();
