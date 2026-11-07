// The order form (new order and edit draft) and the Confirm / Cancel buttons on an order page.
// Needs api.js loaded first (csrfToken, apiRequest).
//
// The totals shown here are a preview only. The server ignores any totals or rates the browser
// could send: it gets only customer_id, discount_percent and [{product_id, quantity}], and
// works out every amount itself. Every check here is repeated on the server.

// ---------------------------------------------------------------------------
// Money in whole paise
// ---------------------------------------------------------------------------
// JavaScript numbers are floats (0.1 + 0.2 is 0.30000000000000004), so money is kept as a
// whole number of paise: "1500.50" -> 150050. Integer sums are exact.

// "1500.5" -> 150050. Also used for the discount: "10.5" -> 1050 hundredths of a percent.
// Returns null if the text isn't a number with at most 2 decimal places.
function toHundredths(text) {
  const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(String(text).trim());
  if (!match) {
    return null;
  }
  const whole = Number(match[1]);
  const fraction = Number((match[2] || "").padEnd(2, "0"));
  return whole * 100 + fraction;
}

// 150050 -> "1500.50"
function formatPaise(paise) {
  const rupees = Math.floor(paise / 100);
  const rest = String(paise % 100).padStart(2, "0");
  return rupees + "." + rest;
}

// numerator / denominator rounded to a whole number, halves going up (same rule as the server).
// For numbers zero or more: floor(n/d + 1/2) = floor((2n + d) / 2d).
function divideRoundHalfUp(numerator, denominator) {
  return Math.floor((numerator * 2 + denominator) / (denominator * 2));
}

// "3" -> 3. Returns null for anything that isn't a whole number like 1, 2, 3.
function parseWholeNumber(text) {
  const value = String(text).trim();
  return /^\d+$/.test(value) ? Number(value) : null;
}

const MAX_DISCOUNT_HUNDREDTHS = 2000; // 20.00 %

// ---------------------------------------------------------------------------
// The order form
// ---------------------------------------------------------------------------

function setupOrderForm(form) {
  const orderId = form.dataset.orderId; // "" for a new order
  const customerSelect = form.querySelector("#customer_id");
  const discountInput = form.querySelector("#discount_percent");
  const rowsBody = form.querySelector("#item-rows");
  const addRowButton = form.querySelector("#add-row");
  const saveButton = form.querySelector("#save-button");
  const formMessage = form.querySelector("#form-message");
  const rowTemplate = document.getElementById("item-row-template");

  // The order being edited (null for a new order).
  const existingOrder = JSON.parse(document.getElementById("order-data").textContent);

  // A product already on the order keeps the rate stored when it was added; the server does
  // the same. Any other product uses today's price. {product_id: rate in paise}
  const storedRates = {};
  if (existingOrder) {
    existingOrder.items.forEach(function (item) {
      storedRates[item.product.id] = toHundredths(item.rate);
    });
  }

  function allRows() {
    return Array.from(rowsBody.querySelectorAll(".item-row"));
  }

  // --- rows ---

  function addRow(item) {
    const row = rowTemplate.content.firstElementChild.cloneNode(true);
    const productSelect = row.querySelector(".product-select");
    const quantityInput = row.querySelector(".quantity-input");

    productSelect.addEventListener("change", function () {
      loadProduct(row);
    });
    quantityInput.addEventListener("input", function () {
      clearRowError(row, "quantity");
      updateTotals();
    });
    row.querySelector(".remove-row").addEventListener("click", function () {
      row.remove();
      updateTotals();
    });

    rowsBody.appendChild(row);
    if (item) {
      productSelect.value = String(item.product.id);
      quantityInput.value = item.quantity;
      loadProduct(row);
    }
    updateTotals();
  }

  // Show the chosen product's rate and stock. Fetches GET /api/products/<id>.
  async function loadProduct(row) {
    const productSelect = row.querySelector(".product-select");
    const rateCell = row.querySelector(".rate-cell");
    const stockCell = row.querySelector(".stock-cell");
    const productId = productSelect.value;

    clearRowError(row, "product");
    row.dataset.ratePaise = "";
    rateCell.textContent = "-";
    stockCell.textContent = "-";

    if (productId === "") {
      updateTotals();
      return;
    }

    // The same product may not be on two rows. The server checks this too.
    const usedElsewhere = allRows().some(function (other) {
      return other !== row && other.querySelector(".product-select").value === productId;
    });
    if (usedElsewhere) {
      productSelect.value = "";
      showRowError(row, "product", "This product is already in the order. Change the quantity on its row instead.");
      updateTotals();
      return;
    }

    rateCell.textContent = "Loading...";
    const result = await apiRequest("GET", "/api/products/" + productId);

    // The user may have picked another product while we waited. Then this answer is stale.
    if (productSelect.value !== productId) {
      return;
    }

    if (!result.ok) {
      rateCell.textContent = "-";
      const message = result.status === 404
        ? "This product is no longer available. Choose another one."
        : result.data.error;
      showRowError(row, "product", message);
      updateTotals();
      return;
    }

    const product = result.data;
    const ratePaise = productId in storedRates ? storedRates[productId] : toHundredths(product.price);
    row.dataset.ratePaise = String(ratePaise);
    rateCell.textContent = formatPaise(ratePaise);
    stockCell.textContent = product.stock_quantity;
    updateTotals();
  }

  // --- live totals (preview) ---

  function updateTotals() {
    let subtotal = 0;
    allRows().forEach(function (row) {
      const quantity = parseWholeNumber(row.querySelector(".quantity-input").value);
      const rate = row.dataset.ratePaise ? Number(row.dataset.ratePaise) : null;
      let amount = 0;
      if (quantity !== null && rate !== null) {
        amount = quantity * rate;
      }
      row.querySelector(".amount-cell").textContent = formatPaise(amount);
      subtotal += amount;
    });

    // An invalid discount counts as 0 in the preview; saving shows the error.
    let discountHundredths = discountText() === "" ? 0 : toHundredths(discountText());
    if (discountHundredths === null || discountHundredths > MAX_DISCOUNT_HUNDREDTHS) {
      discountHundredths = 0;
    }
    // discount = subtotal x percent / 100, and percent = hundredths / 100.
    const discount = divideRoundHalfUp(subtotal * discountHundredths, 10000);

    form.querySelector("#subtotal").textContent = formatPaise(subtotal);
    form.querySelector("#discount-amount").textContent = formatPaise(discount);
    form.querySelector("#grand-total").textContent = formatPaise(subtotal - discount);
  }

  function discountText() {
    return discountInput.value.trim();
  }

  // --- messages ---

  function showRowError(row, kind, message) {
    // kind is "product" or "quantity"
    row.querySelector("." + kind + "-error").textContent = message;
    const field = kind === "product" ? row.querySelector(".product-select") : row.querySelector(".quantity-input");
    field.classList.add("invalid");
  }

  function clearRowError(row, kind) {
    row.querySelector("." + kind + "-error").textContent = "";
    const field = kind === "product" ? row.querySelector(".product-select") : row.querySelector(".quantity-input");
    field.classList.remove("invalid");
  }

  function clearErrors() {
    formMessage.hidden = true;
    formMessage.textContent = "";
    form.querySelectorAll("[data-error-for]").forEach(function (element) {
      element.textContent = "";
    });
    customerSelect.classList.remove("invalid");
    discountInput.classList.remove("invalid");
    allRows().forEach(function (row) {
      clearRowError(row, "product");
      clearRowError(row, "quantity");
    });
  }

  // errors: {field: message}, with the same keys the server uses:
  // "customer_id", "discount_percent", "items", "items[0].product_id", "items[0].quantity".
  function showErrors(message, errors) {
    clearErrors();
    const rows = allRows();
    const unplaced = []; // messages with no field on the page; shown at the top

    Object.keys(errors).forEach(function (key) {
      const rowMatch = /^items\[(\d+)\]\.(product_id|quantity)$/.exec(key);
      if (rowMatch && rows[Number(rowMatch[1])]) {
        const kind = rowMatch[2] === "product_id" ? "product" : "quantity";
        showRowError(rows[Number(rowMatch[1])], kind, errors[key]);
        return;
      }
      const slot = form.querySelector('[data-error-for="' + key + '"]');
      if (slot) {
        slot.textContent = errors[key];
        if (key === "customer_id") customerSelect.classList.add("invalid");
        if (key === "discount_percent") discountInput.classList.add("invalid");
      } else {
        unplaced.push(errors[key]);
      }
    });

    formMessage.textContent = [message].concat(unplaced).join(" ");
    formMessage.hidden = false;
    formMessage.scrollIntoView({ block: "nearest" });
  }

  // --- checks before saving (the server repeats all of them) ---

  function validate() {
    const errors = {};

    if (customerSelect.value === "") {
      errors.customer_id = "Choose a customer.";
    }

    if (discountText() !== "") {
      const hundredths = toHundredths(discountText());
      if (hundredths === null || hundredths > MAX_DISCOUNT_HUNDREDTHS) {
        errors.discount_percent = "Enter a number from 0 to 20, with at most 2 decimal places.";
      }
    }

    const rows = allRows();
    if (rows.length === 0) {
      errors.items = "Add at least one item.";
    }
    const seen = {};
    rows.forEach(function (row, index) {
      const productId = row.querySelector(".product-select").value;
      if (productId === "") {
        errors["items[" + index + "].product_id"] = "Choose a product.";
      } else if (seen[productId]) {
        errors["items[" + index + "].product_id"] = "This product is already in the order.";
      }
      seen[productId] = true;

      const quantity = parseWholeNumber(row.querySelector(".quantity-input").value);
      if (quantity === null || quantity < 1) {
        errors["items[" + index + "].quantity"] = "Enter a whole number, 1 or more.";
      }
    });
    return errors;
  }

  // --- save ---

  async function save(event) {
    event.preventDefault();
    const errors = validate();
    if (Object.keys(errors).length > 0) {
      showErrors("Please fix the problems marked below.", errors);
      return;
    }
    clearErrors();

    // Only what the server needs. No rates or totals: it works those out itself.
    const body = {
      customer_id: Number(customerSelect.value),
      discount_percent: discountText() === "" ? "0" : discountText(),
      items: allRows().map(function (row) {
        return {
          product_id: Number(row.querySelector(".product-select").value),
          quantity: parseWholeNumber(row.querySelector(".quantity-input").value),
        };
      }),
    };

    saveButton.disabled = true; // stops a double click from creating two orders
    saveButton.textContent = "Saving...";
    const result = orderId
      ? await apiRequest("PUT", "/api/orders/" + orderId, body)
      : await apiRequest("POST", "/api/orders", body);

    if (result.ok) {
      // Leave the button disabled: the page is about to change.
      window.location.href = "/orders/" + result.data.id;
      return;
    }

    saveButton.disabled = false;
    saveButton.textContent = "Save draft";
    showErrors(result.data.error, result.status === 422 ? result.data.details : {});
  }

  // --- wire it up ---

  addRowButton.addEventListener("click", function () {
    addRow(null);
  });
  discountInput.addEventListener("input", updateTotals);
  customerSelect.addEventListener("change", function () {
    customerSelect.classList.remove("invalid");
  });
  form.addEventListener("submit", save);

  if (existingOrder) {
    existingOrder.items.forEach(addRow);
  } else {
    addRow(null); // a new order starts with one empty row
  }
}

// ---------------------------------------------------------------------------
// Confirm and Cancel buttons on the order page
// ---------------------------------------------------------------------------

function setupOrderActions(buttons) {
  const messageBox = document.getElementById("action-message");

  function showMessage(message, shortages) {
    messageBox.textContent = message;
    if (shortages && shortages.length > 0) {
      const list = document.createElement("ul");
      shortages.forEach(function (shortage) {
        const line = document.createElement("li");
        line.textContent = shortage.code + ": ordered " + shortage.requested + ", only " + shortage.available + " in stock";
        list.appendChild(line);
      });
      messageBox.appendChild(list);
    }
    messageBox.hidden = false;
  }

  buttons.forEach(function (button) {
    button.addEventListener("click", async function () {
      if (!window.confirm(button.dataset.confirm)) {
        return;
      }
      // Disable every action button until the server answers, so nothing is sent twice.
      buttons.forEach(function (b) { b.disabled = true; });
      messageBox.hidden = true;

      const result = await apiRequest("POST", button.dataset.url);
      if (result.ok) {
        window.location.reload(); // show the new status, read-only
        return;
      }
      showMessage(result.data.error, result.data.details.shortages);
      buttons.forEach(function (b) { b.disabled = false; });
    });
  });
}

// ---------------------------------------------------------------------------
// Start whichever part this page has
// ---------------------------------------------------------------------------

const orderForm = document.getElementById("order-form");
if (orderForm) {
  setupOrderForm(orderForm);
}
const actionButtons = Array.from(document.querySelectorAll("[data-order-action]"));
if (actionButtons.length > 0) {
  setupOrderActions(actionButtons);
}
