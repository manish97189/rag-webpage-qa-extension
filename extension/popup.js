let activeUrl = "";

// Grab the current tab's URL as soon as the popup opens
chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
  if (tabs[0] && tabs[0].url) {
    activeUrl = tabs[0].url;
    document.getElementById("current-url").textContent = activeUrl;
  } else {
    document.getElementById("current-url").textContent = "No accessible page in this tab";
  }
});

document.getElementById("ask-btn").addEventListener("click", async () => {
  const questionInput = document.getElementById("question");
  const askBtn = document.getElementById("ask-btn");
  const answerBox = document.getElementById("answer");
  const question = questionInput.value.trim();

  if (!question) {
    answerBox.style.display = "block";
    answerBox.textContent = "Enter a question first.";
    return;
  }
  if (!activeUrl) {
    answerBox.style.display = "block";
    answerBox.textContent = "Open a webpage before asking a question.";
    return;
  }

  askBtn.disabled = true;
  askBtn.textContent = "Thinking...";
  answerBox.style.display = "block";
  answerBox.textContent = "Loading webpage via WebBaseLoader & generating answer...";

  try {
    const response = await fetch("http://localhost:8000/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: activeUrl, question: question })
    });

    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error(`The server returned an invalid response (HTTP ${response.status}).`);
    }

    if (response.ok) {
      answerBox.textContent = data.answer || "The server returned no answer.";
    } else {
      answerBox.textContent = "Error: " + (data.detail || "Something went wrong.");
    }
  } catch (err) {
    answerBox.textContent = err instanceof TypeError
      ? "Cannot connect to FastAPI server. Make sure uvicorn is running on port 8000."
      : err.message;
  } finally {
    askBtn.disabled = false;
    askBtn.textContent = "Ask LangChain";
  }
});