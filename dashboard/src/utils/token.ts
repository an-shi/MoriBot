const TOKEN_KEY = 'moribot.token'

let memoryToken: string | null = null

function readStorage(storage: Storage): string | null {
  try {
    return storage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function getToken(): string | null {
  if (memoryToken) {
    return memoryToken
  }
  memoryToken = readStorage(localStorage) || readStorage(sessionStorage)
  return memoryToken
}

export function setToken(token: string, remember: boolean): void {
  memoryToken = token
  try {
    localStorage.removeItem(TOKEN_KEY)
    sessionStorage.removeItem(TOKEN_KEY)
    const storage = remember ? localStorage : sessionStorage
    storage.setItem(TOKEN_KEY, token)
  } catch {
    // Storage can be unavailable in hardened browsers; the in-memory token
    // still keeps the current tab authenticated.
  }
}

export function clearToken(): void {
  memoryToken = null
  try {
    localStorage.removeItem(TOKEN_KEY)
    sessionStorage.removeItem(TOKEN_KEY)
  } catch {
    // Ignore storage failures.
  }
}
