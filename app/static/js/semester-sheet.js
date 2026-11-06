(()=>{
 const form=document.querySelector('[data-semester-sheet]');if(!form)return;
 const round=n=>Math.round((n+Number.EPSILON)*100)/100;
 const equivalent=n=>{for(const [threshold,grade] of [[98,'1.00'],[95,'1.25'],[92,'1.50'],[89,'1.75'],[86,'2.00'],[83,'2.25'],[80,'2.50'],[77,'2.75'],[75,'3.00']])if(n>=threshold)return grade;return '5.00';};
 const rows=[...form.querySelectorAll('[data-student-row]')];
 const help=document.getElementById('sheet-cell-help');
 const activityMenus=[...form.querySelectorAll('.activity-menu')];
 const closeActivityMenus=()=>activityMenus.forEach(menu=>{const panel=menu.querySelector(':scope > div');if(panel.matches(':popover-open'))panel.hidePopover();menu.open=false;menu.closest('th').classList.remove('activity-actions-visible');menu.closest('th').querySelector('.sheet-activity-reveal')?.setAttribute('aria-expanded','false');menu.querySelector('summary').setAttribute('aria-expanded','false');});
 activityMenus.forEach(menu=>{
  const trigger=menu.querySelector('summary'),panel=menu.querySelector(':scope > div');
  const number=menu.closest('th').querySelector('.sheet-activity-reveal');
  number?.addEventListener('click',event=>{
   if(!matchMedia('(hover: none)').matches&&event.pointerType!=='touch'&&event.detail!==0)return;
   const show=!menu.closest('th').classList.contains('activity-actions-visible');closeActivityMenus();
   menu.closest('th').classList.toggle('activity-actions-visible',show);number.setAttribute('aria-expanded',String(show));
   if(show&&event.detail===0)trigger.focus();
  });
  panel.setAttribute('popover','manual');trigger.setAttribute('aria-expanded','false');
  trigger.addEventListener('click',event=>{
   event.preventDefault();const wasOpen=menu.open;closeActivityMenus();if(wasOpen)return;
   menu.open=true;trigger.setAttribute('aria-expanded','true');panel.showPopover();
   const rect=trigger.getBoundingClientRect(),bounds=panel.getBoundingClientRect();
   panel.style.left=Math.max(8,Math.min(rect.right-bounds.width,innerWidth-bounds.width-8))+'px';
   panel.style.top=(rect.bottom+bounds.height+8<=innerHeight?rect.bottom+4:Math.max(8,rect.top-bounds.height-4))+'px';
  });
  panel.addEventListener('click',event=>{if(event.target.closest('button'))closeActivityMenus();});
 });
 document.addEventListener('click',event=>{if(!event.target.closest('.activity-menu,.sheet-activity-reveal'))closeActivityMenus();});
 document.addEventListener('keydown',event=>{if(event.key==='Escape'){const open=activityMenus.find(menu=>menu.open);closeActivityMenus();open?.querySelector('summary').focus();}});
 window.addEventListener('scroll',closeActivityMenus,true);
 window.addEventListener('resize',closeActivityMenus);
 const addDialog=document.getElementById('component-add-dialog'),editDialog=document.getElementById('component-edit-dialog');
 let dialogTrigger=null;
 const enableDialog=(dialog,enabled)=>dialog.querySelectorAll('input').forEach(input=>input.disabled=!enabled);
 const dialogValid=dialog=>[...dialog.querySelectorAll('input')].every(input=>input.reportValidity());
 const allocated=()=>round([...form.querySelectorAll('[data-parent-edit]')].filter(e=>e.dataset.parentEdit!==form.elements.delete_category_id?.value).reduce((sum,e)=>sum+(Number(e.value)||0),0));
 const allocationMessage=total=>total>100?`${total}% allocated — exceeds 100% by ${round(total-100)}%. Reduce the component percentages before saving.`:total<100?`${total}% allocated — ${round(100-total)}% remaining. Complete exactly 100% before publishing.`:'100% allocated — complete.';
 const checkAllocation=dialog=>{
  const input=dialog===addDialog?form.elements.new_category_weight:editDialog.querySelector('[data-editor-weight]');
  const base=allocated()-(dialog===editDialog?Number(form.elements[`cat__${editDialog.dataset.category}__weight`].value):0);
  const projected=round(base+(Number(input.value)||0));input.setCustomValidity(projected>100?allocationMessage(projected):'');
  dialog.querySelector('[data-allocation-warning]').textContent=allocationMessage(projected);return projected<=100;
 };
 document.querySelector('[data-component-add]')?.addEventListener('click',event=>{
  dialogTrigger=event.currentTarget;addDialog.dataset.saving='false';enableDialog(addDialog,true);checkAllocation(addDialog);addDialog.showModal();addDialog.querySelector('input').focus();
 });
 form.querySelectorAll('[data-component-edit]').forEach(button=>button.addEventListener('click',()=>{
  dialogTrigger=button;const id=button.dataset.componentEdit;editDialog.dataset.category=id;editDialog.dataset.saving='false';
  editDialog.querySelector('[data-editor-name]').value=form.elements[`cat__${id}__name`].value;
  editDialog.querySelector('[data-editor-weight]').value=form.elements[`cat__${id}__weight`].value;
  editDialog.querySelector('[data-editor-count-output]').textContent=form.elements[`cat__${id}__count`].value+' activities';
  enableDialog(editDialog,true);checkAllocation(editDialog);editDialog.showModal();editDialog.querySelector('input').focus();
 }));
 [addDialog,editDialog].filter(Boolean).forEach(dialog=>{
  dialog.addEventListener('input',event=>{event.stopPropagation();checkAllocation(dialog);});
  dialog.querySelectorAll('[data-close-component]').forEach(button=>button.addEventListener('click',()=>dialog.close()));
  dialog.addEventListener('keydown',event=>{if(event.key==='Enter'&&event.target.matches('input')){event.preventDefault();dialog.querySelector('[data-save-new-component],[data-save-component-edit]').click();}});
  dialog.addEventListener('close',()=>{
   if(dialog.dataset.saving==='true')return;
   enableDialog(dialog,false);
   if(dialog===addDialog){form.elements.new_category_name.value='';form.elements.new_category_weight.value='';form.elements.new_category_count.value='1';}
   recalculate();dialogTrigger?.focus();
  });
 });
 form.querySelector('[data-save-new-component]')?.addEventListener('click',()=>{
  if(!checkAllocation(addDialog)||!dialogValid(addDialog))return;addDialog.dataset.saving='true';addDialog.close();
  form.dispatchEvent(new Event('input',{bubbles:true}));form.requestSubmit();
 });
 form.querySelector('[data-save-component-edit]')?.addEventListener('click',()=>{
  if(!checkAllocation(editDialog)||!dialogValid(editDialog))return;const id=editDialog.dataset.category;
  for(const [field,selector] of [['name','[data-editor-name]'],['weight','[data-editor-weight]']])form.elements[`cat__${id}__${field}`].value=editDialog.querySelector(selector).value;
  enableDialog(editDialog,false);editDialog.dataset.saving='true';editDialog.close();form.dispatchEvent(new Event('input',{bubbles:true}));form.requestSubmit();
 });
 form.querySelectorAll('[data-insert-activity]').forEach(button=>button.addEventListener('click',()=>{
  const input=form.elements[`cat__${button.dataset.insertActivity}__count`];const current=Number(input.dataset.currentCount)===0&&input.value==='1'?0:Number(input.value);
  if(current>=50){help.textContent='A component can contain at most 50 activities.';return;}
  input.value=current+1;form.dispatchEvent(new Event('input',{bubbles:true}));
  help.textContent='Adding activity '+input.value+'. The new date and highest possible score will start blank.';
  form.requestSubmit();
 }));
 form.querySelectorAll('[data-delete-activity]').forEach(button=>button.addEventListener('click',()=>{
  if(!confirm('Delete this activity column and ALL student scores recorded in it? This cannot be undone. Other activity columns will be kept.'))return;
  let consent=form.elements.confirm_delete_activity;if(!consent){consent=document.createElement('input');consent.type='hidden';consent.name='confirm_delete_activity';form.appendChild(consent);}consent.value='yes';
  let input=form.elements.delete_activity_id;if(!input){input=document.createElement('input');input.type='hidden';input.name='delete_activity_id';form.appendChild(input);}input.value=button.dataset.deleteActivity;form.requestSubmit();
 }));
 const deleteDialog=document.getElementById('component-delete-dialog');
 form.querySelectorAll('[data-component-remove]').forEach(button=>button.addEventListener('click',()=>{
  dialogTrigger=button;deleteDialog.dataset.saving='false';deleteDialog.dataset.category=button.dataset.componentRemove;const id=button.dataset.componentRemove;
  const hasScores=button.dataset.hasScores==='true'||[...form.querySelectorAll(`input[data-category="${id}"]`)].some(input=>input.value!=='');
  deleteDialog.dataset.hasScores=String(hasScores);deleteDialog.querySelector('[data-confirm-score-deletion]').checked=false;
  deleteDialog.querySelector('[data-delete-score-consent]').hidden=!hasScores;
  deleteDialog.querySelector('[data-delete-description]').textContent='Delete “'+form.elements[`cat__${id}__name`].value+'” and all its activity columns?';
  deleteDialog.querySelector('[data-confirm-component-delete]').disabled=hasScores;deleteDialog.showModal();deleteDialog.querySelector('[data-cancel-component-delete]').focus();
 }));
 deleteDialog?.querySelector('[data-confirm-score-deletion]').addEventListener('change',event=>deleteDialog.querySelector('[data-confirm-component-delete]').disabled=!event.target.checked);
 deleteDialog?.querySelectorAll('[data-cancel-component-delete]').forEach(button=>button.addEventListener('click',()=>deleteDialog.close()));
 deleteDialog?.addEventListener('close',()=>{if(deleteDialog.dataset.saving!=='true'){for(const name of ['delete_category_id','confirm_delete','confirm_delete_scores'])form.elements[name]?.remove();recalculate();dialogTrigger?.focus();}});
 deleteDialog?.querySelector('[data-confirm-component-delete]').addEventListener('click',()=>{
  if(deleteDialog.dataset.hasScores==='true'&&!deleteDialog.querySelector('[data-confirm-score-deletion]').checked)return;
  for(const [name,value] of [['delete_category_id',deleteDialog.dataset.category],['confirm_delete','yes'],['confirm_delete_scores',deleteDialog.dataset.hasScores==='true'?'yes':'no']]){
   let input=form.elements[name];if(!input){input=document.createElement('input');input.type='hidden';input.name=name;form.appendChild(input);}input.value=value;
  }
  deleteDialog.dataset.saving='true';deleteDialog.close();form.dispatchEvent(new Event('input',{bubbles:true}));form.requestSubmit();
 });
 const recalculate=()=>{
  const maxima=[...form.querySelectorAll('[data-maximum-edit]')];
  const parents=[...form.querySelectorAll('[data-parent-edit]')];
  const totalAllocation=round(allocated()+(form.elements.new_category_weight&&!form.elements.new_category_weight.disabled?Number(form.elements.new_category_weight.value)||0:0));
  const allocation=document.getElementById('component-allocation');if(allocation){allocation.textContent=allocationMessage(totalAllocation);allocation.classList.toggle('over',totalAllocation>100);}
  parents.forEach(input=>input.setCustomValidity(totalAllocation>100?allocationMessage(totalAllocation):''));
  const points=form.dataset.aggregation==='POINTS';
  let calculable=parents.length?totalAllocation<=100&&parents.every(input=>input.value!==''&&input.checkValidity()):form.dataset.valid==='true';
  let valid=parents.length?round(parents.reduce((sum,e)=>sum+Number(e.value),0))===100:form.dataset.valid==='true';
  parents.forEach(parent=>{
   const weights=[...form.querySelectorAll('[data-weight-edit]')].filter(e=>e.dataset.group===parent.dataset.parentEdit);
   if(!points&&round(weights.reduce((sum,e)=>sum+Number(e.value),0))>100)calculable=false;
   if(Number(parent.value)>0&&(!weights.length||!points&&round(weights.reduce((sum,e)=>sum+Number(e.value),0))!==100))valid=false;
  });
  maxima.forEach(max=>{
   const id=max.dataset.maximumEdit;
   if(!max.value||!max.checkValidity())valid=false;
   const weight=form.querySelector(`[data-weight-edit="${id}"]`);
   const title=form.querySelector(`[name="activity__${id}__name"]`);
   form.querySelectorAll(`input[data-activity="${id}"]`).forEach(input=>{
    input.max=max.value||'0';input.dataset.maximum=max.value||'0';input.dataset.weight=weight.value;input.dataset.activityName=title.value;
    input.title=title.value+' · score out of '+(max.value||'unset HPS');
   });
  });
  if(maxima.length)form.querySelectorAll('[data-hps-total]').forEach(cell=>{const items=maxima.filter(e=>e.dataset.group===cell.dataset.hpsTotal);cell.textContent=items.some(e=>!e.value)?'—':round(items.reduce((sum,e)=>sum+Number(e.value),0));});
  if([...form.querySelectorAll('thead input')].some(e=>!e.checkValidity()))valid=false;
  if([...form.querySelectorAll('[data-count-edit]')].some(e=>Number(e.value)!==Number(e.dataset.currentCount))||form.elements.new_category_name?.value.trim())valid=false;
  rows.forEach(row=>{
   let total=0,rowValid=calculable,hasConfigured=false,missing=false;
   row.querySelectorAll('[data-weighted]').forEach(cell=>{
    const id=cell.dataset.weighted;let raw=0,percentage=0,maximumTotal=0,groupValid=true;
    const parent=form.querySelector(`[data-parent-edit="${id}"]`);
    if(parent){cell.dataset.parentWeight=parent.value;form.querySelector(`[data-hps-weight="${id}"]`).textContent=parent.value+'%';}
    row.querySelectorAll(`input[data-category="${id}"]`).forEach(input=>{
     const score=input.value===''?0:Number(input.value),maximum=Number(input.dataset.maximum);
     if(input.value==='')missing=true;
     if(!input.checkValidity()||maximum<=0&&input.value!==''){rowValid=false;groupValid=false;}
     if(maximum>0)hasConfigured=true;
     raw+=Number.isFinite(score)?score:0;
     if(maximum>0){percentage+=(score/maximum)*Number(input.dataset.weight);maximumTotal+=maximum;}
    });
    if(points)percentage=maximumTotal>0?round(raw/maximumTotal*100):0;
    const weighted=points?round(percentage*Number(cell.dataset.parentWeight)/100):percentage*Number(cell.dataset.parentWeight)/100;total+=weighted;
    row.querySelector(`[data-raw-total="${id}"]`).textContent=round(raw);
    row.querySelector(`[data-percentage="${id}"]`).textContent=groupValid&&maximumTotal>0?round(percentage).toFixed(2):'—';
    cell.textContent=groupValid&&maximumTotal>0?round(weighted).toFixed(2):'—';
   });
   rowValid=rowValid&&hasConfigured&&total>=0&&round(total)<=100;
   const result=round(total);row.querySelector('[data-semester-total]').textContent=rowValid?Math.round(result).toString():'—';
   row.querySelector('[data-university-grade]').textContent=rowValid?equivalent(result):'—';
   row.querySelector('[data-remarks]').textContent=rowValid?(!valid||missing?'In progress':result>=75?'Passed':'Failed'):'Set HPS';
  });
 };
 form.addEventListener('focusin',event=>{if(!event.target.matches('input[data-activity-name]'))return;if(help)help.textContent=event.target.dataset.activityName+' · Highest possible score: '+(Number(event.target.dataset.maximum)||'set HPS first');});
 form.addEventListener('input',recalculate);
 // Enter and vertical arrows stay in the same activity column, as in a worksheet.
 form.addEventListener('keydown',e=>{
  if(!e.target.matches('input[data-activity]')||!['Enter','ArrowUp','ArrowDown'].includes(e.key))return;
  e.preventDefault();e.stopImmediatePropagation();
  const index=rows.indexOf(e.target.closest('[data-student-row]'));
  const next=rows[index+((e.key==='ArrowUp'||e.key==='Enter'&&e.shiftKey)?-1:1)];
  next?.querySelector(`input[data-activity="${e.target.dataset.activity}"]`)?.focus();
 },true);
 form.addEventListener('paste',e=>{
  if(!e.target.matches('input[data-activity]'))return;
  const value=e.clipboardData.getData('text/plain');if(!/[\t\n\r]/.test(value))return;
  e.preventDefault();
  const grid=value.replace(/\r/g,'').replace(/\n$/,'').split('\n').map(line=>line.split('\t'));
  const origin=rows.indexOf(e.target.closest('[data-student-row]'));
  const column=[...rows[origin].querySelectorAll('input[data-activity]')].indexOf(e.target);const edits=[];
  for(let r=0;r<grid.length;r++)for(let c=0;c<grid[r].length;c++){
   const input=rows[origin+r]?.querySelectorAll('input[data-activity]')[column+c],raw=grid[r][c].trim();
   if(!input||input.disabled||raw!==''&&(!/^\d+$/.test(raw)||Number(input.dataset.maximum)<=0||Number(raw)>Number(input.max))){help.textContent='Paste cancelled: check the range, highest possible scores, and score limits. No cells were changed.';return;}
   edits.push([input,raw]);
  }
  edits.forEach(([input,raw])=>input.value=raw);e.target.dispatchEvent(new Event('input',{bubbles:true}));help.textContent=edits.length+' score cells pasted. Save sheet to store your changes.';
 });
 recalculate();
})();
