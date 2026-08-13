const conversationEl = document.getElementById("conversation");
const emptyStateEl = document.getElementById("empty-state");
const repoInfoEl = document.getElementById("repo-info");
const questionEl = document.getElementById("question");
const askButton = document.getElementById("ask-button");

// Cosmetic only — the backend answers in one request, not a stream of tool
// events — but cycling through what the ReAct loop is plausibly doing reads
// far better than a static "loading" label while genuinely waiting ~10-15s,
// and hints at the tool-calling loop underneath. See Design.md's "Thinking
// state" spec.
const THINKING_PHRASES = ["searching code…", "checking history…", "reading source…", "weighing citations…"];

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
  body.appendChild(thinking);
  message.appendChild(body);
  conversationEl.appendChild(message);

  let i = 0;
  const renderLine = () => {
    thinking.textContent = "";
    const line = document.createElement("span");
    line.className = "thinking-line";
    line.textContent = THINKING_PHRASES[i % THINKING_PHRASES.length];
    thinking.appendChild(line);
    i += 1;
  };
  renderLine();
  const intervalId = window.setInterval(renderLine, 2200);

  return { message, stopThinking: () => window.clearInterval(intervalId) };
}

function buildStrataBar(citations) {
  const codeCount = citations.filter((c) => c.source === "code").length;
  const historyCount = citations.filter((c) => c.source === "history").length;
  if (codeCount + historyCount === 0) return null;

  const bar = document.createElement("div");
  bar.className = "strata-bar";

  const segments = [];
  if (codeCount > 0) {
    const seg = document.createElement("div");
    seg.className = "strata-segment strata-segment-code";
    seg.dataset.source = "code";
    seg.style.flex = String(codeCount);
    bar.appendChild(seg);
    segments.push(seg);
  }
  if (historyCount > 0) {
    const seg = document.createElement("div");
    seg.className = "strata-segment strata-segment-history";
    seg.dataset.source = "history";
    seg.style.flex = String(historyCount);
    bar.appendChild(seg);
    segments.push(seg);
  }

  // Only worth wiring hover-linking when there's an actual mix to distinguish
  if (segments.length > 1) {
    for (const seg of segments) {
      seg.addEventListener("mouseenter", () => {
        bar.classList.add("dimmed");
        seg.classList.add("emphasized");
        for (const chip of bar._chips || []) {
          chip.classList.toggle("emphasized", chip.dataset.source === seg.dataset.source);
        }
      });
      seg.addEventListener("mouseleave", () => {
        bar.classList.remove("dimmed");
        seg.classList.remove("emphasized");
        for (const chip of bar._chips || []) {
          chip.classList.remove("emphasized");
        }
      });
    }
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
  expanded.dataset.source = citation.source;

  const eyebrow = document.createElement("div");
  eyebrow.className = "citation-eyebrow";
  eyebrow.textContent = citation.source === "history" ? "history" : "code";

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
  return { wrapper, chip };
}

function renderAnswer(thinkingHandle, answer, citations) {
  thinkingHandle.stopThinking();
  const { message } = thinkingHandle;
  const body = message.querySelector(".answer-body");
  body.textContent = "";

  const strataBar = buildStrataBar(citations);
  if (strataBar) {
    message.insertBefore(strataBar, body);
  }

  const answerText = document.createElement("div");
  answerText.className = "answer-text";
  answerText.textContent = answer;
  body.appendChild(answerText);

  if (citations.length > 0) {
    const citationsEl = document.createElement("div");
    citationsEl.className = "citations";
    const chips = [];
    for (const citation of citations) {
      const { wrapper, chip } = buildCitationChip(citation);
      citationsEl.appendChild(wrapper);
      chips.push(chip);
    }
    body.appendChild(citationsEl);
    if (strataBar) strataBar._chips = chips;
  }
}

function renderError(thinkingHandle, message) {
  thinkingHandle.stopThinking();
  const body = thinkingHandle.message.querySelector(".answer-body");
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
  const thinkingHandle = addThinkingMessage();
  conversationEl.scrollTop = conversationEl.scrollHeight;

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!response.ok) {
      renderError(thinkingHandle, `Couldn't reach the model. (${response.status})`);
      return;
    }
    const data = await response.json();
    renderAnswer(thinkingHandle, data.answer, data.citations);
  } catch (err) {
    renderError(thinkingHandle, `Couldn't reach the model. ${err.message}`);
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
