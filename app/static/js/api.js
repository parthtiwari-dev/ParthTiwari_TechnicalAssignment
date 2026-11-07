// Small helpers for calling the JSON API from a page. Plain JavaScript, no framework.

// The CSRF token that base.html puts in <meta name="csrf-token">.
// The server refuses a POST or PUT without it, so another site can't send one for the user.
function csrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.content : "";
}

// Call the API. Always resolves to { ok, status, data }, never throws:
// - ok is true for a 2xx answer, and data is the JSON the server sent
// - on an error, data is { error: "message", details: {...} }
// - if the server can't be reached at all, status is 0
async function apiRequest(method, url, body) {
  const options = {
    method: method,
    headers: { Accept: "application/json" },
    credentials: "same-origin", // send the login cookie
  };
  if (method !== "GET") {
    options.headers["X-CSRFToken"] = csrfToken();
  }
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(url, options);
  } catch (networkError) {
    return {
      ok: false,
      status: 0,
      data: { error: "Could not reach the server. Check your connection and try again.", details: {} },
    };
  }

  let data;
  try {
    data = await response.json();
  } catch (notJson) {
    data = {};
  }

  if (!response.ok) {
    data.details = data.details || {};
    if (response.status === 401) {
      data.error = "Your session has ended. Please log in again.";
    } else if (!data.error) {
      data.error = "Something went wrong (error " + response.status + "). Please try again.";
    }
  }
  return { ok: response.ok, status: response.status, data: data };
}
