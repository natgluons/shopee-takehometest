const receiptsBody = document.getElementById("receipts-body");
const receiptsEmpty = document.getElementById("receipts-empty");
const receiptsStatus = document.getElementById("receipts-status");

function money(cents, currency = "USD") {
  if (cents === null || cents === undefined) return "-";
  return `${currency} ${(Number(cents) / 100).toFixed(2)}`;
}

function barList(container, entries, formatter) {
  container.replaceChildren();
  if (!entries.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "No data yet.";
    container.appendChild(empty);
    return;
  }
  const max = Math.max(...entries.map((entry) => entry.value), 1);
  entries.forEach((entry) => {
    const row = document.createElement("div");
    row.className = "bar-row";
    const label = document.createElement("span");
    label.className = "bar-label";
    label.textContent = entry.label;
    const track = document.createElement("span");
    track.className = "bar-track";
    const fill = document.createElement("span");
    fill.className = "bar-fill";
    fill.style.width = `${Math.max(4, (entry.value / max) * 100)}%`;
    track.appendChild(fill);
    const value = document.createElement("span");
    value.className = "bar-value";
    value.textContent = formatter(entry);
    row.append(label, track, value);
    container.appendChild(row);
  });
}

async function loadInsights() {
  const response = await fetch("/api/insights");
  if (!response.ok) return;
  const data = await response.json();
  document.getElementById("stat-receipts").textContent = String(data.receipt_count || 0);
  const totals = (data.totals || [])
    .map((item) => money(item.total_cents, item.currency))
    .join(", ");
  document.getElementById("stat-total").textContent = totals || "0.00";
  const topMerchant = (data.by_merchant || [])[0];
  document.getElementById("stat-merchant").textContent = topMerchant
    ? `${topMerchant.merchant} (${money(topMerchant.total_cents)})`
    : "-";

  barList(
    document.getElementById("merchant-bars"),
    (data.by_merchant || []).map((item) => ({
      label: item.merchant,
      value: item.total_cents,
      currency: item.currency || "USD",
      count: item.receipt_count,
    })),
    (entry) => money(entry.value, entry.currency)
  );
  barList(
    document.getElementById("item-bars"),
    (data.top_items || []).map((item) => ({
      label: item.description,
      value: item.occurrences,
      count: item.total_cents,
    })),
    (entry) => `${entry.value}x`
  );
}

function renderReceipts(receipts) {
  receiptsBody.replaceChildren();
  receiptsEmpty.hidden = receipts.length !== 0;
  receipts.forEach((receipt) => {
    const row = document.createElement("tr");

    const date = document.createElement("td");
    date.textContent = receipt.purchase_date;

    const merchant = document.createElement("td");
    merchant.textContent = receipt.merchant;

    const items = document.createElement("td");
    items.className = "items-cell";
    items.textContent = (receipt.items || [])
      .map((item) => item.description)
      .join(", ") || "No items";

    const total = document.createElement("td");
    total.className = "num";
    total.textContent = money(receipt.total_cents, receipt.currency);

    const actions = document.createElement("td");
    const remove = document.createElement("button");
    remove.className = "icon-button";
    remove.type = "button";
    remove.textContent = "Delete";
    remove.addEventListener("click", async () => {
      if (!window.confirm(`Delete receipt #${receipt.id}?`)) return;
      const response = await fetch(`/api/receipts/${receipt.id}`, { method: "DELETE" });
      if (!response.ok) {
        receiptsStatus.textContent = "Delete failed.";
        return;
      }
      await refresh();
    });
    actions.appendChild(remove);

    row.append(date, merchant, items, total, actions);
    receiptsBody.appendChild(row);
  });
}

async function loadReceipts() {
  const params = new URLSearchParams();
  const dateFrom = document.getElementById("filter-from").value;
  const dateTo = document.getElementById("filter-to").value;
  const merchant = document.getElementById("filter-merchant").value.trim();
  const item = document.getElementById("filter-item").value.trim();
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  if (merchant) params.set("merchant", merchant);
  if (item) params.set("item", item);
  receiptsStatus.textContent = "Loading...";
  try {
    const response = await fetch(`/api/receipts?${params.toString()}`);
    const data = await response.json();
    if (!response.ok) {
      receiptsStatus.textContent = data.detail || "Could not load receipts.";
      return;
    }
    renderReceipts(data.receipts || []);
    receiptsStatus.textContent =
      data.count === 0 ? "No receipts matched the filters." : `${data.count} receipt(s) shown.`;
  } catch (error) {
    receiptsStatus.textContent = `Request failed: ${error}`;
  }
}

async function refresh() {
  await Promise.all([loadInsights(), loadReceipts()]);
}

document.getElementById("filter-form").addEventListener("submit", (event) => {
  event.preventDefault();
  loadReceipts();
});
document.getElementById("clear-filters").addEventListener("click", () => {
  document.getElementById("filter-form").reset();
  loadReceipts();
});

refresh();
