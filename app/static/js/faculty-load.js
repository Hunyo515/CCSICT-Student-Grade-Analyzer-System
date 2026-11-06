(()=>{
 const panel=document.getElementById('faculty-load-panel'),content=document.getElementById('faculty-load-content');
 if(!panel||!content)return;
 let controller,opener,previousOverflow='',version=0;
 const load=async link=>{
  controller?.abort();controller=new AbortController();const requestVersion=++version;
  content.replaceChildren();content.setAttribute('aria-busy','true');
  const loading=document.createElement('p');loading.setAttribute('role','status');loading.textContent='Loading assigned classes…';content.append(loading);
  try{
   const url=new URL(link.href);url.searchParams.set('panel','1');
   const response=await fetch(url,{signal:controller.signal,credentials:'same-origin'});
   if(!response.ok||response.redirected)throw new Error('Unable to load assigned classes.');
   const html=await response.text();if(requestVersion!==version||!panel.open)return;
   content.innerHTML=html;
  }catch(error){
   if(error.name==='AbortError'||requestVersion!==version||!panel.open)return;
   const message=document.createElement('p');message.setAttribute('role','alert');message.textContent='Unable to load assigned classes. Please try again.';
   const retry=document.createElement('button');retry.type='button';retry.className='btn btn-outline';retry.textContent='Try again';retry.onclick=()=>load(link);
   const fallback=document.createElement('a');fallback.href=link.href;fallback.className='text-action';fallback.textContent='Open full page';
   content.replaceChildren(message,retry,fallback);
  }finally{if(requestVersion===version)content.removeAttribute('aria-busy');}
 };
 document.querySelectorAll('[data-faculty-load]').forEach(link=>link.addEventListener('click',event=>{
  if(event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;
  event.preventDefault();opener=link;
  if(!panel.open){previousOverflow=document.body.style.overflow;document.body.style.overflow='hidden';panel.showModal();}
  load(link);
 }));
 panel.querySelector('[data-close-faculty-load]').onclick=()=>panel.close();
 panel.addEventListener('click',event=>{const rect=panel.getBoundingClientRect();if(event.target===panel&&(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom))panel.close();});
 panel.addEventListener('close',()=>{version++;controller?.abort();content.removeAttribute('aria-busy');document.body.style.overflow=previousOverflow;opener?.focus();});
})();
