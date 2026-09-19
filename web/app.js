'use strict';
const selector = document.querySelector('#edition-select');
selector?.addEventListener('change', () => {
  // Only generated local routes can be selected. No model-provided URL is executable.
  if (/^(index|demo|\d{8}T\d{4}-[a-f0-9]{12})\.html$/.test(selector.value)) location.href = selector.value;
});
function freshness() {
  const body=document.body, note=document.querySelector('#freshness');
  if (body.dataset.demo === 'true') return;
  const now=Date.now(), issued=Date.parse(body.dataset.issued), checked=Date.parse(body.dataset.checked);
  const messages=[];
  if (Number.isFinite(issued) && now-issued > 15*3600000) messages.push('表示資料は発表から15時間以上経過しています。最新資料として扱わず、原資料の日時を確認してください。');
  if (body.dataset.archive !== 'true' && Number.isFinite(checked) && now-checked > 15*3600000) messages.push('自動取得の確認が15時間以上更新されていません。更新処理が止まっている可能性があります。');
  note.textContent=messages.join(' '); note.hidden=!messages.length;
}
freshness(); setInterval(freshness,60000);
const dialog=document.querySelector('#chart-dialog'), img=document.querySelector('#chart-image');
let scale=1, opener;
function zoom(next) {
  scale=Math.max(1,Math.min(4,next));
  img.className='zoom-'+Math.round(scale*2);
}
document.querySelectorAll('.chart-open').forEach(button => button.addEventListener('click', () => {
  opener=button; img.src=button.dataset.src; zoom(1); dialog.showModal();
}));
document.querySelector('#zoom-in')?.addEventListener('click',()=>zoom(scale+.5));
document.querySelector('#zoom-out')?.addEventListener('click',()=>zoom(scale-.5));
document.querySelector('#zoom-reset')?.addEventListener('click',()=>zoom(1));
document.querySelector('#chart-close')?.addEventListener('click',()=>dialog.close());
dialog?.addEventListener('close',()=>opener?.focus());
