document.addEventListener('DOMContentLoaded',()=>{
 document.querySelectorAll('[data-imprimir]').forEach(botao=>botao.addEventListener('click',()=>window.print()));
 let alterado=false;
 document.querySelectorAll('form[data-aviso]').forEach(form=>{
  form.addEventListener('input',()=>{alterado=true;});
  form.addEventListener('change',()=>{alterado=true;});
  form.addEventListener('submit',()=>{alterado=false;});
 });
 window.addEventListener('beforeunload',evento=>{if(alterado){evento.preventDefault();evento.returnValue='';}});
});
