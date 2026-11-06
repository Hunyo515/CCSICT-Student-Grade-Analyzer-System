document.addEventListener('submit',function(event){
 const form=event.target;if(event.defaultPrevented||form.method.toLowerCase()!=='post')return;
 if(form.dataset.submitting==='true'){event.preventDefault();return;}
 if(form.dataset.confirm&&form.dataset.confirmed!=='true'){
  event.preventDefault();const submitter=event.submitter,dialog=document.createElement('dialog');dialog.className='confirm-dialog';
  dialog.innerHTML='<div class="dialog-body"><h2>Confirm action</h2><p></p></div><div class="dialog-actions"><button type="button" class="btn btn-secondary" data-cancel>Cancel</button><button type="button" class="btn btn-primary" data-continue>Continue</button></div>';
  dialog.querySelector('p').textContent=form.dataset.confirm;document.body.appendChild(dialog);
  dialog.querySelector('[data-cancel]').onclick=()=>dialog.close();
  dialog.querySelector('[data-continue]').onclick=()=>{form.dataset.confirmed='true';dialog.close();form.requestSubmit(submitter);};
  dialog.addEventListener('close',()=>{dialog.remove();submitter?.focus();});dialog.showModal();dialog.querySelector('[data-cancel]').focus();return;
 }
 delete form.dataset.confirmed;form.dataset.submitting='true';form.setAttribute('aria-busy','true');
 setTimeout(()=>form.querySelectorAll('button[type=submit],button:not([type])').forEach(button=>{if(!button.disabled){button.disabled=true;button.dataset.busyDisabled='true';}}),0);
});
window.addEventListener('pageshow',()=>document.querySelectorAll('form').forEach(form=>{delete form.dataset.submitting;delete form.dataset.confirmed;form.removeAttribute('aria-busy');form.querySelectorAll('[data-busy-disabled]').forEach(button=>{button.disabled=false;delete button.dataset.busyDisabled;});}));
/* University formats mirror server validation. */
document.querySelectorAll('input').forEach(input=>{
 const rules={id_number:['[0-9]{2}-[0-9]{4}','Use the student ID format 23-2762.'],contact_number:['09[0-9]{9}','Enter 11 digits starting with 09.'],section:['(BSCS|BSIT|BSIS|BSDSA|BLIS) [1-4]-[1-9][0-9]?','Use a university section, e.g. BSDSA 1-1.']};
 if(rules[input.name]){input.pattern=rules[input.name][0];input.title=rules[input.name][1];if(['id_number','contact_number'].includes(input.name))input.inputMode='numeric';if(input.name==='contact_number'){input.maxLength=11;input.required=true;}if(input.name==='id_number')input.maxLength=7;}
 if(['first_name','middle_name','last_name'].includes(input.name))input.maxLength=50;
 if(input.name==='email'&&input.form?.querySelector('[name=program],[name=full_name],[name=first_name]')&&!input.form.action.includes('/settings/')){input.title='Use your institutional email, e.g. alexis.s.balmores@isu.edu.ph.';const check=()=>input.setCustomValidity(input.value&&!/^[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)+@isu\.edu\.ph$/i.test(input.value)?input.title:'');input.addEventListener('input',check);}
 if(['new_password','password'].includes(input.name)&&!input.form?.action.includes('/login/')){input.minLength=8;const check=()=>{const v=input.value;input.setCustomValidity(v&&(!/[A-Z]/.test(v)||!/[a-z]/.test(v)||!/[0-9]/.test(v)||!/[\p{P}\p{S}]/u.test(v)||new TextEncoder().encode(v).length>72)?'Use at least 8 characters with uppercase, lowercase, a number, and a special character.':'');};input.addEventListener('input',check);}
});

// Offer generation at the focused password field, using the browser's secure RNG.
document.addEventListener('DOMContentLoaded',()=>{
 const randomPassword=()=>{
  const groups=['ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz','0123456789','!@#$%*?'];
  const alphabet=groups.join('');
  const pick=(length)=>{const bytes=new Uint8Array(1);do{crypto.getRandomValues(bytes);}while(bytes[0]>=256-(256%length));return bytes[0]%length;};
  let value;
  do{value=Array.from({length:16},()=>alphabet[pick(alphabet.length)]).join('');}while(!groups.every(group=>[...value].some(c=>group.includes(c))));
  return value;
 };
 document.querySelectorAll('[data-random-password]').forEach(input=>{
  const control=input.closest('.password-control');if(!control)return;
  const popup=document.createElement('div');popup.className='password-suggestion';popup.hidden=true;
  popup.id=input.id+'-suggestion';
  const button=document.createElement('button');button.type='button';button.textContent='Generate random password';
  button.dataset.generatePassword=input.id;popup.append(button);control.append(popup);
  input.setAttribute('aria-controls',popup.id);input.setAttribute('aria-expanded','false');
  const show=()=>{popup.hidden=false;input.setAttribute('aria-expanded','true');};
  const hide=()=>{popup.hidden=true;input.setAttribute('aria-expanded','false');};
  input.addEventListener('focus',show);input.addEventListener('click',show);
  control.addEventListener('focusout',event=>{if(!control.contains(event.relatedTarget))hide();});
  control.addEventListener('keydown',event=>{if(event.key==='Escape'){hide();event.preventDefault();}});
  button.addEventListener('click',()=>{
   const password=randomPassword();
   input.form.querySelectorAll('[name=password],[name=confirm_password]').forEach(field=>{
    field.value=password;field.dispatchEvent(new Event('input',{bubbles:true}));
   });
   input.focus();hide();
  });
 });
 document.querySelectorAll('form').forEach(form=>{
  const password=form.querySelector('[name=password]'),confirm=form.querySelector('[name=confirm_password]');
  if(!password||!confirm)return;
  const check=()=>confirm.setCustomValidity(confirm.value&&confirm.value!==password.value?'Passwords do not match.':'');
  password.addEventListener('input',check);confirm.addEventListener('input',check);
 });
});
