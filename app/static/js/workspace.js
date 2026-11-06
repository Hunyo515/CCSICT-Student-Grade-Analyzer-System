document.querySelectorAll('input[type=password]').forEach(input=>{
  const button=document.createElement('button');
  const inside=input.dataset.passwordToggle==='inside';
  const eye='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>';
  const eyeOff='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m3 3 18 18M10.6 5.1A12 12 0 0 1 12 5c6.5 0 10 7 10 7a18 18 0 0 1-3.2 4.2M6.4 6.4A20 20 0 0 0 2 12s3.5 7 10 7a12 12 0 0 0 5.6-1.4M9.9 9.9a3 3 0 0 0 4.2 4.2"/></svg>';
  button.type='button';button.className='password-toggle';
  button.setAttribute('aria-controls',input.id||(input.id='password-'+Math.random().toString(36).slice(2)));
  const update=()=>{
    const visible=input.type==='text';const label=visible?'Hide password':'Show password';
    button.setAttribute('aria-label',label);button.setAttribute('aria-pressed',String(visible));button.title=label;
    if(inside)button.innerHTML=visible?eyeOff:eye;else button.textContent=label;
  };
  button.addEventListener('click',()=>{input.type=input.type==='password'?'text':'password';update();});
  if(inside){
    const control=document.createElement('div');control.className='password-control';
    input.before(control);control.append(input,button);
  }else input.insertAdjacentElement('afterend',button);
  update();
});
document.querySelectorAll('[data-unsaved]').forEach(form=>{let dirty=false;form.addEventListener('input',()=>{dirty=true;const state=document.getElementById('save-state');if(state)state.textContent='Unsaved changes';});form.addEventListener('submit',()=>{dirty=false;});window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});form.addEventListener('keydown',e=>{if(e.target.matches('input[name^=mark__]')&&e.key==='Enter'){e.preventDefault();const cells=[...form.querySelectorAll('input[name^=mark__]')];const next=cells[cells.indexOf(e.target)+(e.shiftKey?-1:1)];if(next)next.focus();}});});
document.querySelectorAll('button[data-confirm]').forEach(button=>button.addEventListener('click',event=>{if(!confirm(button.dataset.confirm))event.preventDefault();}));
