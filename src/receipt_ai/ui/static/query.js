const form = document.getElementById("query-form");
const questionInput = document.getElementById("question");
const asOfInput = document.getElementById("as-of");
const askButton = document.getElementById("ask-button");
const statusLine = document.getElementById("query-status");
const answerCard = document.getElementById("answer-card");
const answerText = document.getElementById("answer-text");
const answerMeta = document.getElementById("answer-meta");
const answerWarnings = document.getElementById("answer-warnings");
const evidenceList = document.getElementById("evidence-list");
const toolCalls = document.getElementById("tool-calls");

const today = new Date();
const isoToday = new Date(today.getTime() - today.getTimezoneOffset() * 60000)
  .toISOString()
  .slice(0, 10);
asOfInput.value = isoToday;

function pill(text) {
  const element = document.createElement("span");
  element.className = "pill";
  element.textContent = text;
  return element;
}

function evidenceItem(entry) {
  const li = document.createElement("li");
  if (entry.type === "item") {
    li.textContent = `${entry.description} at ${entry.merchant} on ${entry.purchase_date} for ${entry.currency} ${entry.line_total}`;
    return li;
  }
  const items = (entry.items || []).map((item) => item.description).join(", ");
  li.textContent = `${entry.merchant} on ${entry.purchase_date}: ${entry.currency} ${entry.total}${items ? ` (${items})` : ""}`;
  return li;
}

function renderAnswer(data) {
  answerCard.hidden = false;
  answerText.textContent = data.answer;
  answerMeta.replaceChildren(
    pill(data.found ? "Found matching receipts" : "No matching receipts"),
    pill(`engine: ${data.engine}`),
    pill(`as of ${data.as_of}`)
  );
  answerMeta.firstChild.classList.add(data.found ? "pill-success" : "pill-empty");

  answerWarnings.replaceChildren();
  if ((data.warnings || []).length) {
    const list = document.createElement("ul");
    data.warnings.forEach((warning) => {
      const item = document.createElement("li");
      item.textContent = warning;
      list.appendChild(item);
    });
    answerWarnings.append(list);
    answerWarnings.hidden = false;
  } else {
    answerWarnings.hidden = true;
  }

  evidenceList.replaceChildren();
  if (!(data.evidence || []).length) {
    const item = document.createElement("li");
    item.className = "muted";
    item.textContent = "No evidence rows. The tool returned an empty result.";
    evidenceList.appendChild(item);
  } else {
    data.evidence.forEach((entry) => evidenceList.appendChild(evidenceItem(entry)));
  }
  toolCalls.textContent = JSON.stringify(data.tool_calls || [], null, 2);
  answerCard.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function ask() {
  const question = questionInput.value.trim();
  if (!question) {
    statusLine.textContent = "Type a question first.";
    statusLine.className = "status-inline error";
    return;
  }
  askButton.disabled = true;
  statusLine.textContent = "Consulting the receipt tools...";
  statusLine.className = "status-inline";
  try {
    const response = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        as_of: asOfInput.value || null,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      const details = data.problems ? ` ${data.problems.join(" ")}` : "";
      statusLine.textContent = `${data.detail || "Query failed"}.${details}`;
      statusLine.className = "status-inline error";
      return;
    }
    statusLine.textContent = "";
    renderAnswer(data);
  } catch (error) {
    statusLine.textContent = `Query failed: ${error}`;
    statusLine.className = "status-inline error";
  } finally {
    askButton.disabled = false;
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  ask();
});

document.querySelectorAll(".example").forEach((button) => {
  button.addEventListener("click", () => {
    questionInput.value = button.textContent;
    ask();
  });
});
