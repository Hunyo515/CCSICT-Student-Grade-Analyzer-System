document.querySelectorAll('.trend-plot').forEach(plot => {
  const start = Date.parse(plot.dataset.first);
  const span = Date.parse(plot.dataset.last) - start;
  const points = Array.from(plot.querySelectorAll('circle'), point => {
    const x = span ? 40 + 428 * (Date.parse(point.dataset.date) - start) / span : 254;
    point.setAttribute('cx', x);
    return [x, point.getAttribute('cy')].join(',');
  });
  plot.querySelector('polyline').setAttribute('points', points.join(' '));
});
document.querySelector('#trend-subject')?.addEventListener('change', event => {
  document.querySelectorAll('.trend-series').forEach((series,index) => {
    series.hidden = index !== Number(event.target.value);
  });
});
