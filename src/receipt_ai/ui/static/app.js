const state = { items: [], receiptId: null };

const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const chooseFile = document.getElementById("choose-file");
const fileName = document.getElementById("file-name");
const preview = document.getElementById("preview");
const uploadStatus = document.getElementById("upload-status");
const reviewSection = document.getElementById("review-section");
const reviewForm = document.getElementById("review-form");
const itemsBody = document.getElementById("items-body");
const warningsBox = document.getElementById("review-warnings");
const ocrMeta = document.getElementById("ocr-meta");
const saveStatus = document.getElementById("save-status");

function toCents(value) {
  if (value === null || value === undefined) return 0;
  const cleaned = String(value).replace(/[^0-9.\-]/g, "");
  if (!cleaned) return 0;
  const parsed = Number.parseFloat(cleaned);
  if (!Number.isFinite(parsed)) return 0;
  return Math.round(parsed * 100);
}

function fromCents(cents) {
  return (Number(cents || 0) / 100).toFixed(2);
}

function setStatus(element, message, kind = "") {
  element.hidden = !message;
  element.textContent = message;
  element.classList.remove("error", "success");
  if (kind) element.classList.add(kind);
}

function itemLineTotal(item) {
  return Math.round(Number(item.quantity || 0) * Number(item.unit_price_cents || 0));
}

function recalc() {
  const subtotal = state.items.reduce((sum, item) => sum + itemLineTotal(item), 0);
  const tax = toCents(document.getElementById("tax").value);
  document.getElementById("subtotal-display").textContent = fromCents(subtotal);
  document.getElementById("total").value = fromCents(subtotal + tax);
}

function renderItems() {
  itemsBody.replaceChildren();
  state.items.forEach((item, index) => {
    const row = document.createElement("tr");

    const descriptionCell = document.createElement("td");
    const description = document.createElement("input");
    description.value = item.description || "";
    description.dataset.index = String(index);
    description.dataset.field = "description";
    description.setAttribute("aria-label", "Item description");
    descriptionCell.appendChild(description);

    const quantityCell = document.createElement("td");
    quantityCell.className = "num";
    const quantity = document.createElement("input");
    quantity.type = "number";
    quantity.min = "0.01";
    quantity.step = "0.01";
    quantity.value = String(item.quantity || 1);
    quantity.dataset.index = String(index);
    quantity.dataset.field = "quantity";
    quantity.setAttribute("aria-label", "Item quantity");
    quantityCell.appendChild(quantity);

    const unitCell = document.createElement("td");
    unitCell.className = "num";
    const unit = document.createElement("input");
    unit.value = fromCents(item.unit_price_cents);
    unit.inputMode = "decimal";
    unit.dataset.index = String(index);
    unit.dataset.field = "unit_price";
    unit.setAttribute("aria-label", "Item unit price");
    unitCell.appendChild(unit);

    const lineCell = document.createElement("td");
    lineCell.className = "num";
    lineCell.textContent = fromCents(itemLineTotal(item));

    const removeCell = document.createElement("td");
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "icon-button";
    remove.textContent = "Remove";
    remove.dataset.remove = String(index);
    removeCell.appendChild(remove);

    row.append(descriptionCell, quantityCell, unitCell, lineCell, removeCell);
    itemsBody.appendChild(row);
  });
  recalc();
}

function renderReview(payload) {
  const receipt = payload.receipt;
  state.receiptId = receipt.id;
  state.items = (receipt.items || []).map((item) => ({
    description: item.description,
    quantity: item.quantity || 1,
    unit_price_cents: item.unit_price_cents ?? item.line_total_cents ?? 0,
  }));

  document.getElementById("receipt-id").value = String(receipt.id);
  document.getElementById("merchant").value = receipt.merchant || "";
  document.getElementById("purchase-date").value = receipt.purchase_date || "";
  document.getElementById("currency").value = receipt.currency || "USD";
  document.getElementById("tax").value = fromCents(receipt.tax_cents);
  document.getElementById("source-image").value = receipt.source_image || "";
  document.getElementById("raw-text").value = receipt.raw_text || "";
  document.getElementById("raw-text-display").textContent = receipt.raw_text || "(no text)";
  renderItems();

  ocrMeta.replaceChildren();
  const pills = [
    `OCR: ${payload.ocr?.engine || "local"}`,
    `Time: ${(payload.ocr?.duration_seconds || 0).toFixed(2)}s`,
    `Image: ${payload.upload?.width || "?"}x${payload.upload?.height || "?"}`,
  ];
  pills.forEach((text) => {
    const pill = document.createElement("span");
    pill.className = "pill";
    pill.textContent = text;
    ocrMeta.appendChild(pill);
  });

  const warnings = payload.warnings || [];
  warningsBox.replaceChildren();
  if (warnings.length) {
    const title = document.createElement("strong");
    title.textContent = "Review these extraction warnings";
    const list = document.createElement("ul");
    warnings.forEach((warning) => {
      const entry = document.createElement("li");
      entry.textContent = warning;
      list.appendChild(entry);
    });
    warningsBox.append(title, list);
    warningsBox.hidden = false;
  } else {
    warningsBox.hidden = true;
  }

  reviewSection.hidden = false;
  reviewSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function uploadFile(file) {
  if (!file) return;
  fileName.textContent = file.name;
  if (file.type.startsWith("image/")) {
    preview.src = URL.createObjectURL(file);
    preview.hidden = false;
  }
  setStatus(uploadStatus, "Running local OCR and extraction...");
  const form = new FormData();
  form.append("file", file);
  try {
    const response = await fetch("/api/receipts/upload", { method: "POST", body: form });
    const payload = await response.json();
    if (!response.ok) {
      const details = payload.problems ? ` ${payload.problems.join(" ")}` : "";
      setStatus(uploadStatus, `${payload.detail || "Upload failed"}.${details}`, "error");
      return;
    }
    setStatus(uploadStatus, `Extracted receipt #${payload.receipt.id}. Review below.`, "success");
    renderReview(payload);
  } catch (error) {
    setStatus(uploadStatus, `Upload failed: ${error}`, "error");
  }
}

async function saveReceipt(event) {
  event.preventDefault();
  const saveButton = document.getElementById("save-receipt");
  const subtotal = state.items.reduce((sum, item) => sum + itemLineTotal(item), 0);
  const tax = toCents(document.getElementById("tax").value);
  const payload = {
    merchant: document.getElementById("merchant").value.trim(),
    purchase_date: document.getElementById("purchase-date").value,
    currency: document.getElementById("currency").value.trim().toUpperCase(),
    subtotal_cents: subtotal,
    tax_cents: tax,
    total_cents: subtotal + tax,
    source_image: document.getElementById("source-image").value || null,
    raw_text: document.getElementById("raw-text").value || "",
    status: "saved",
    items: state.items.map((item) => ({
      description: item.description,
      quantity: Number(item.quantity) || 1,
      unit_price_cents: Number(item.unit_price_cents) || 0,
      line_total_cents: itemLineTotal(item),
    })),
  };
  if (!payload.merchant || !payload.purchase_date || payload.items.length === 0) {
    setStatus(saveStatus, "Merchant, date, and at least one item are required.", "error");
    return;
  }
  saveButton.disabled = true;
  setStatus(saveStatus, "Saving...");
  try {
    const response = await fetch(`/api/receipts/${state.receiptId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) {
      const details = result.problems ? ` ${result.problems.join(" ")}` : "";
      setStatus(saveStatus, `${result.detail || "Save failed"}.${details}`, "error");
      return;
    }
    setStatus(saveStatus, `Saved receipt #${result.receipt.id}.`, "success");
    window.setTimeout(() => {
      window.location.href = "/history";
    }, 700);
  } catch (error) {
    setStatus(saveStatus, `Save failed: ${error}`, "error");
  } finally {
    saveButton.disabled = false;
  }
}

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") fileInput.click();
});
chooseFile.addEventListener("click", (event) => {
  event.stopPropagation();
  fileInput.click();
});
fileInput.addEventListener("change", () => uploadFile(fileInput.files[0]));

["dragenter", "dragover"].forEach((name) => {
  dropzone.addEventListener(name, (event) => {
    event.preventDefault();
    dropzone.classList.add("dragging");
  });
});
["dragleave", "drop"].forEach((name) => {
  dropzone.addEventListener(name, (event) => {
    event.preventDefault();
    dropzone.classList.remove("dragging");
  });
});
dropzone.addEventListener("drop", (event) => uploadFile(event.dataTransfer.files[0]));

itemsBody.addEventListener("input", (event) => {
  const target = event.target;
  if (!target.dataset || target.dataset.index === undefined) return;
  const index = Number(target.dataset.index);
  const item = state.items[index];
  if (!item) return;
  if (target.dataset.field === "description") item.description = target.value;
  if (target.dataset.field === "quantity") item.quantity = Number(target.value) || 0;
  if (target.dataset.field === "unit_price") item.unit_price_cents = toCents(target.value);
  renderItems();
});

itemsBody.addEventListener("click", (event) => {
  const index = event.target.dataset?.remove;
  if (index === undefined) return;
  state.items.splice(Number(index), 1);
  renderItems();
});

document.getElementById("add-item").addEventListener("click", () => {
  state.items.push({ description: "", quantity: 1, unit_price_cents: 0 });
  renderItems();
});
document.getElementById("tax").addEventListener("input", recalc);
reviewForm.addEventListener("submit", saveReceipt);
