// 产品自己的演示交互；不包含任何监测工具逻辑。
let recognizing=false,hasContent=false;
const tabs=[...document.querySelectorAll('[role="tab"]')];
function selectTab(tab){
  tabs.forEach(item=>{
    const active=item===tab;
    item.setAttribute('aria-selected',String(active));
    item.tabIndex=active?0:-1;
    document.getElementById(item.getAttribute('aria-controls')).hidden=!active;
  });
  const isSummary=tab.id==='summary-tab';
  document.querySelector('#save-content').hidden=!isSummary;
  document.querySelector('#recognition-controls').hidden=isSummary;
}
tabs.forEach((tab,index)=>{
  tab.tabIndex=index===0?0:-1;
  tab.addEventListener('click',()=>selectTab(tab));
  tab.addEventListener('keydown',event=>{
    if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
    event.preventDefault();
    const next=tabs[event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length];
    next.focus();next.click();
  });
});
document.querySelector('#recognize').addEventListener('click',event=>{
  recognizing=!recognizing;
  if(recognizing)hasContent=true;
  event.currentTarget.setAttribute('aria-pressed',String(recognizing));
  document.querySelector('#record-label').textContent=recognizing?'关闭识别':'开始识别';
  for(const prefix of ['transcript','summary']){
    document.getElementById(`${prefix}-empty`).hidden=hasContent;
    document.getElementById(`${prefix}-content`).hidden=!hasContent;
  }
});
