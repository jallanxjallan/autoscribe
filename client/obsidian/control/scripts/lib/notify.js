function notify(message, timeout = 4000) {
  try {
    const NoticeClass = globalThis.Notice;

    if (typeof NoticeClass === "function") {
      new NoticeClass(message, timeout);
      return;
    }
  } catch (_) {}

  console.log(message);
}

module.exports = {
  notify
};