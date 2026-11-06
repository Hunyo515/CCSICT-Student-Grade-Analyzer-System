(()=>{
 const dialog=document.getElementById('profilePhotoDialog');if(!dialog)return;
 const form=document.getElementById('profilePhotoForm'),input=form.querySelector('[type=file]'),preview=document.getElementById('photoPreview'),empty=document.getElementById('photoPreviewEmpty'),zoom=document.getElementById('photoZoom'),save=document.getElementById('saveProfilePhoto'),status=document.getElementById('photoUploadStatus');let trigger=null;
 document.querySelectorAll('.profile-photo-trigger').forEach(button=>button.addEventListener('click',()=>{trigger=button;dialog.showModal();}));
 dialog.querySelectorAll('[data-photo-cancel]').forEach(button=>button.addEventListener('click',()=>dialog.close()));
 dialog.addEventListener('close',()=>{input.value='';input.setCustomValidity('');preview.hidden=true;preview.removeAttribute('src');empty.hidden=false;zoom.value='1';zoom.disabled=true;save.disabled=true;preview.style.transform='scale(1)';status.textContent='JPG, PNG or WebP · up to 2 MB. Your photo changes only after you save.';trigger?.focus();});
 input.addEventListener('change',()=>{
  const file=input.files[0];save.disabled=true;input.setCustomValidity('');if(!file)return;
  if(file.size>2*1024*1024||!['image/jpeg','image/png','image/webp'].includes(file.type)){status.textContent='Choose a JPG, PNG or WebP photo smaller than 2 MB.';input.value='';return;}
  const reader=new FileReader();reader.onload=()=>preview.src=reader.result;reader.onerror=()=>status.textContent='This photo could not be read.';reader.readAsDataURL(file);
 });
 preview.onload=()=>{if(preview.naturalWidth*preview.naturalHeight>16000000){status.textContent='Choose a photo up to 16 megapixels.';return;}preview.hidden=false;empty.hidden=true;zoom.value='1';zoom.disabled=false;preview.style.transform='scale(1)';save.disabled=false;status.textContent='Adjust the zoom, then save your profile picture.';};
 preview.onerror=()=>{save.disabled=true;status.textContent='This file could not be opened as a photo.';};
 zoom.addEventListener('input',()=>preview.style.transform=`scale(${zoom.value})`);
 save.addEventListener('click',()=>{
  if(!preview.naturalWidth||save.disabled)return;save.disabled=true;
  const canvas=document.createElement('canvas');canvas.width=512;canvas.height=512;const context=canvas.getContext('2d'),side=Math.min(preview.naturalWidth,preview.naturalHeight)/Number(zoom.value);
  context.fillStyle='#fff';context.fillRect(0,0,512,512);context.drawImage(preview,(preview.naturalWidth-side)/2,(preview.naturalHeight-side)/2,side,side,0,0,512,512);
  canvas.toBlob(blob=>{if(!blob){save.disabled=false;status.textContent='Could not prepare the photo. Choose it again.';return;}const transfer=new DataTransfer();transfer.items.add(new File([blob],'profile.jpg',{type:'image/jpeg'}));input.files=transfer.files;form.requestSubmit();},'image/jpeg',0.9);
 });
})();
