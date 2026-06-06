function getNodeModule(name) {
  try {
    if (typeof require === "function") return require(name);
  } catch (err) {}

  try {
    if (typeof window !== "undefined" && window.require) {
      return window.require(name);
    }
  } catch (err) {}

  return null;
}

function requireNodeModule(name) {
  const mod = getNodeModule(name);
  if (!mod) {
    throw new Error(`Node module unavailable: ${name}`);
  }
  return mod;
}

module.exports = {
  getNodeModule,
  requireNodeModule,
};