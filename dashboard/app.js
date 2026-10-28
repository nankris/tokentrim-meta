'use strict';
const el = id => document.getElementById(id);
const metrics = [
  {key: 'tokens', label: 'Tokens', format: n => n.toLocaleString(undefined, {maximumFractionDigits: 1})},
  {key: 'dollars', label: 'Dollars / task', format: n => '$' + n.toFixed(6)},
  {key: 'pass_rate', label: 'Pass rate', format: n => (n * 100).toFixed(1) + '%'}
];
function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function interval(value, format) {
  return value?.ci95 ? `${format(value.ci95[0])} to ${format(value.ci95[1])}` : 'undefined';
}
function estimate(value, format) {
  return value?.mean == null ? 'undefined' : `${format(value.mean)} [${interval(value, format)}]`;
}
function validate(data) {
  if (!data.metadata || !Array.isArray(data.results) || !data.summary) throw Error('Expected TokenTrim results schema.');
  for (const metric of metrics) {
    for (const mode of ['baseline', 'tokentrim']) {
      const v = data.summary[mode]?.[metric.key];
      if (!v || !Number.isFinite(v.mean) || !Array.isArray(v.ci95) || v.ci95.length !== 2 || !v.ci95.every(Number.isFinite)) throw Error('Invalid summary values.');
    }
    if (!data.summary.paired?.[metric.key]?.difference) throw Error('Missing paired confidence intervals.');
  }
}
function render(data) {
  validate(data);
  const fake = data.metadata.data_kind === 'FAKE' || data.metadata.usage_simulated || data.metadata.checks_simulated;
  el('badge').textContent = fake ? 'FAKE · simulated benchmark' : 'CUSTOM · inspect provenance';
  el('notice').textContent = data.metadata.notice || 'Custom benchmark data.';
  el('cards').replaceChildren(); el('summary').replaceChildren(); el('tasks').replaceChildren();
  for (const metric of metrics) {
    const card = node('section', undefined, 'card');
    card.append(node('h2', metric.label));
    const maximum = Math.max(data.summary.baseline[metric.key].mean, data.summary.tokentrim[metric.key].mean, 1e-12);
    for (const mode of ['baseline', 'tokentrim']) {
      const value = data.summary[mode][metric.key];
      const label = node('div', undefined, 'bar-label');
      label.append(node('span', mode === 'baseline' ? 'Baseline' : 'TokenTrim'), node('strong', metric.format(value.mean)));
      const track = node('div', undefined, 'track');
      const bar = node('div', undefined, mode === 'baseline' ? 'bar' : 'bar trim');
      bar.style.width = Math.max(0, Math.min(100, value.mean / maximum * 100)) + '%';
      track.append(bar);
      card.append(label, track, node('div', '95% CI: ' + interval(value, metric.format), 'ci'));
    }
    el('cards').append(card);
    const paired = data.summary.paired[metric.key];
    const diffFormat = metric.key === 'pass_rate' ? n => (n * 100).toFixed(1) + ' pp' : metric.format;
    const row = node('tr');
    [metric.label, estimate(data.summary.baseline[metric.key], metric.format),
      estimate(data.summary.tokentrim[metric.key], metric.format), estimate(paired.difference, diffFormat),
      metric.key === 'pass_rate' ? '—' : estimate(paired.percent_saving, n => n.toFixed(1) + '%')
    ].forEach(text => row.append(node('td', text)));
    el('summary').append(row);
  }
  for (const result of data.results) {
    const row = node('tr');
    [result.task_id, result.mode, result.tokens, result.usage.cached_input, '$' + result.dollars.toFixed(6),
      `${result.passed ? 'Pass' : 'Fail'}${data.metadata.checks_simulated ? ' (FAKE)' : ''}`
    ].forEach(text => row.append(node('td', text)));
    el('tasks').append(row);
  }
  const bootstrap = data.metadata.bootstrap || {};
  el('method').textContent = `${data.metadata.task_count} tasks · ${bootstrap.samples} resamples · seed ${bootstrap.seed} · ${bootstrap.method}.`;
  el('status').textContent = 'Loaded ' + (fake ? 'FAKE' : 'custom') + ' results.';
  el('results').hidden = false;
}
function failure(error) {
  el('results').hidden = true;
  el('badge').textContent = 'Results unavailable';
  el('status').textContent = `${error.message} Serve the repo with python3 -m http.server, or choose a local results file.`;
}
async function reload() {
  try {
    const response = await fetch('../results/results.json', {cache: 'no-store'});
    if (!response.ok) throw Error(`Could not load results (${response.status}).`);
    render(await response.json());
  } catch (error) { failure(error); }
}
el('reload').addEventListener('click', reload);
el('file').addEventListener('change', async event => {
  const file = event.target.files[0];
  if (!file) return;
  try { render(JSON.parse(await file.text())); } catch (error) { failure(error); }
});
reload();
