const questionEl = document.getElementById("question");
const answerEl = document.getElementById("answer");
const citationsEl = document.getElementById("citations");
const askButton = document.getElementById("ask-button");

function renderCitations(citations) {
  citationsEl.textContent = "";
  if (!citations || citations.length === 0) {
    citationsEl.textContent = "(none)";
    return;
  }

  for (const citation of citations) {
    const wrapper = document.createElement("div");

    const button = document.createElement("button");
    button.textContent = `[${citation.source}] ${citation.label}`;

    const expanded = document.createElement("pre");
    expanded.hidden = true;
    expanded.textContent = citation.text;

    button.addEventListener("click", () => {
      expanded.hidden = !expanded.hidden;
    });

    wrapper.appendChild(button);
    wrapper.appendChild(expanded);
    citationsEl.appendChild(wrapper);
  }
}

async function ask() {
  const question = questionEl.value.trim();
  if (!question) return;

  askButton.disabled = true;
  answerEl.textContent = "Thinking...";
  citationsEl.textContent = "";

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!response.ok) {
      answerEl.textContent = `Error: request failed (${response.status})`;
      return;
    }
    const data = await response.json();
    answerEl.textContent = data.answer;
    renderCitations(data.citations);
  } catch (err) {
    answerEl.textContent = `Error: ${err.message}`;
  } finally {
    askButton.disabled = false;
  }
}

askButton.addEventListener("click", ask);
questionEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    ask();
  }
});
