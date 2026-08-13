const conversationEl = document.getElementById("conversation");
const emptyStateEl = document.getElementById("empty-state");
const repoInfoEl = document.getElementById("repo-info");
const questionEl = document.getElementById("question");
const askButton = document.getElementById("ask-button");

async function loadRepoInfo() {
  try {
    const response = await fetch("/info");
    if (!response.ok) return;
    const data = await response.json();
    repoInfoEl.textContent = `${data.repo} · ${data.chunk_count.toLocaleString()} chunks`;
  } catch {
    // repo info is a nice-to-have; a failed fetch just leaves the header blank
  }
}

function addUserMessage(question) {
  const message = document.createElement("div");
  message.className = "message message-user";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = question;
  message.appendChild(bubble);
  conversationEl.appendChild(message);
  return message;
}

function addThinkingMessage() {
  const message = document.createElement("div");
  message.className = "message message-answer";
  const body = document.createElement("div");
  body.className = "answer-body";
  const thinking = document.createElement("div");
  thinking.className = "thinking";
  thinking.textContent = "thinking…";
  body.appendChild(thinking);
  message.appendChild(body);
  conversationEl.appendChild(message);
  return message;
}

function buildStrataBar(citations) {
  const codeCount = citations.filter((c) => c.source === "code").length;
  const historyCount = citations.filter((c) => c.source === "history").length;
  if (codeCount + historyCount === 0) return null;

  const bar = document.createElement("div");
  bar.className = "strata-bar";
  if (codeCount > 0) {
    const seg = document.createElement("div");
    seg.className = "strata-segment-code";
    seg.style.flex = String(codeCount);
    bar.appendChild(seg);
  }
  if (historyCount > 0) {
    const seg = document.createElement("div");
    seg.className = "strata-segment-history";
    seg.style.flex = String(historyCount);
    bar.appendChild(seg);
  }
  return bar;
}

function buildCitationChip(citation) {
  const wrapper = document.createElement("div");

  const chip = document.createElement("button");
  chip.className = "citation-chip";
  chip.type = "button";
  chip.dataset.source = citation.source;
  chip.textContent = citation.label;

  const expanded = document.createElement("div");
  expanded.className = "citation-expanded";

  const eyebrow = document.createElement("div");
  eyebrow.className = "citation-eyebrow";
  eyebrow.textContent = citation.label;

  const body = document.createElement("pre");
  body.className = "citation-body";
  body.textContent = citation.text;

  expanded.appendChild(eyebrow);
  expanded.appendChild(body);

  chip.addEventListener("click", () => {
    expanded.classList.toggle("open");
  });

  wrapper.appendChild(chip);
  wrapper.appendChild(expanded);
  return wrapper;
}

function renderAnswer(thinkingMessage, answer, citations) {
  const body = thinkingMessage.querySelector(".answer-body");
  body.textContent = "";

  const strataBar = buildStrataBar(citations);
  if (strataBar) {
    thinkingMessage.insertBefore(strataBar, body);
  }

  const answerText = document.createElement("div");
  answerText.className = "answer-text";
  answerText.textContent = answer;
  body.appendChild(answerText);

  if (citations.length > 0) {
    const citationsEl = document.createElement("div");
    citationsEl.className = "citations";
    for (const citation of citations) {
      citationsEl.appendChild(buildCitationChip(citation));
    }
    body.appendChild(citationsEl);
  }
}

function renderError(thinkingMessage, message) {
  const body = thinkingMessage.querySelector(".answer-body");
  body.textContent = "";
  const errorText = document.createElement("div");
  errorText.className = "answer-text error-text";
  errorText.textContent = message;
  body.appendChild(errorText);
}

async function ask(question) {
  if (!question) return;

  emptyStateEl.style.display = "none";
  askButton.disabled = true;

  addUserMessage(question);
  const thinkingMessage = addThinkingMessage();
  conversationEl.scrollTop = conversationEl.scrollHeight;

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!response.ok) {
      renderError(thinkingMessage, `Couldn't reach the model. (${response.status})`);
      return;
    }
    const data = await response.json();
    renderAnswer(thinkingMessage, data.answer, data.citations);
  } catch (err) {
    renderError(thinkingMessage, `Couldn't reach the model. ${err.message}`);
  } finally {
    askButton.disabled = false;
    conversationEl.scrollTop = conversationEl.scrollHeight;
  }
}

function askFromInput() {
  const question = questionEl.value.trim();
  questionEl.value = "";
  ask(question);
}

askButton.addEventListener("click", askFromInput);
questionEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    askFromInput();
  }
});

document.querySelectorAll(".example-chip").forEach((chip) => {
  chip.addEventListener("click", () => ask(chip.textContent));
});

loadRepoInfo();
