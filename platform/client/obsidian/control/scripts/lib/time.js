function formatRelativeTime(ms) {
  const delta = Date.now() - ms;

  if (!Number.isFinite(delta) || delta < 0) return "just now";

  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;
  const week = 7 * day;

  if (delta < minute) return "just now";

  if (delta < hour) {
    const n = Math.floor(delta / minute);
    return `${n}m`;
  }

  if (delta < day) {
    const h = Math.floor(delta / hour);
    const m = Math.floor((delta % hour) / minute);
    return m ? `${h}h ${m}m` : `${h}h`;
  }

  if (delta < week) {
    const d = Math.floor(delta / day);
    const h = Math.floor((delta % day) / hour);
    return h ? `${d}d ${h}h` : `${d}d`;
  }

  const w = Math.floor(delta / week);
  const d = Math.floor((delta % week) / day);

  return d ? `${w}w ${d}d ago` : `${w}w`;
}

module.exports = {
  formatRelativeTime
};