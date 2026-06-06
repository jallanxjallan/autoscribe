function compactTimestamp(date = new Date()) {
  const pad = value => String(value).padStart(2, "0");

  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
    pad(date.getHours()),
    pad(date.getMinutes()),
    pad(date.getSeconds())
  ].join("");
}

function randomToken(length = 6) {
  const alphabet = "abcdefghijklmnopqrstuvwxyz0123456789";
  let token = "";

  for (let index = 0; index < length; index += 1) {
    token += alphabet[Math.floor(Math.random() * alphabet.length)];
  }

  return token || "x0";
}

function generateJobId({ prefix = "job", date = new Date(), tokenLength = 6 } = {}) {
  return `${prefix}.${compactTimestamp(date)}.${randomToken(tokenLength)}`;
}

module.exports = {
  compactTimestamp,
  randomToken,
  generateJobId,
};
