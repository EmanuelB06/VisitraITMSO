function readCookie(name) {
  const prefix = `${name}=`;
  const match = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix));
  return match ? decodeURIComponent(match.slice(prefix.length)) : "";
}

async function parseError(response) {
  try {
    const data = await response.json();
    if (data && typeof data.error === "string") return data.error;
  } catch {
    /* Not every error response is JSON. */
  }
  if (response.status === 403) return "Your session expired. Refresh the page and sign in again.";
  return `Request failed (${response.status}).`;
}

export async function getJSON(url) {
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
    credentials: "same-origin",
  });
  if (!response.ok) throw new Error(await parseError(response));
  return response.json();
}

export async function postJSON(url, payload = {}) {
  const response = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": readCookie("csrftoken"),
    },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || (await parseError(response)));
  return data;
}
