export function shouldBlockNavigation(dirty: boolean) { return dirty }

export function attemptNavigation(dirty: boolean, action: () => void) {
  if (shouldBlockNavigation(dirty)) return false
  action()
  return true
}

export function confirmNavigation(action: (() => void) | null) { action?.() }
