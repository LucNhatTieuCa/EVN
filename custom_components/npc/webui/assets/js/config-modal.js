// Per-customer names are saved in HA, separately from Electric Meter mappings.
function showMsg(msg,error=false){const node=document.getElementById('msg');if(node){node.textContent=msg;node.className='msg'+(error?' error':'');}}
let nameAccount='',nameSequence=0,expectedName='';
const currentNameAccount=()=>document.getElementById('accountSelect')?.value||'';
async function nameAPI(method,account,body){const response=await window.EVNApi.fetch(`/api/npc/customer-name/${encodeURIComponent(account)}`,{method,headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const data=await response.json();if(!response.ok)throw new Error(data.error||`Không tải được tên (${response.status}).`);return data;}
function applyCustomerName(data){
    const select=document.getElementById('accountSelect');
    const option=[...select.options].find(o=>o.value===data.account);
    if(option){option.dataset.customerName=data.name;option.textContent=data.name===data.account?data.account:`${data.name} · ${data.account}`;}
    const selected=select.selectedOptions[0];
    const header=document.getElementById('customerHeader');
    if(header)header.textContent=selected?.dataset.customerName||select.value||'EVN MONITOR';
}
async function loadConfig(){
    const account=currentNameAccount(),run=++nameSequence;nameAccount=account;
    const input=document.getElementById('customer_name'),save=document.getElementById('customerNameSave');
    document.getElementById('customerNameAccount').textContent=account;input.disabled=true;save.disabled=true;showMsg('Đang tải tên khách hàng…');
    if(!account){input.value='';showMsg('Chọn mã khách hàng trước.',true);return;}
    try{
        const data=await nameAPI('GET',account);
        if(run!==nameSequence||account!==nameAccount)return;
        expectedName=data.custom_name;input.value=data.custom_name||data.official_name||'';input.placeholder=data.official_name||'Nhập tên dễ nhớ cho mã này';
        document.getElementById('customerNameHint').textContent=data.official_name?`Tên EVN: ${data.official_name}. Để trống để dùng tên EVN.`:'Để trống để dùng mã khách hàng.';
        input.disabled=false;save.disabled=false;showMsg('');applyCustomerName(data);
    }catch(error){if(run===nameSequence)showMsg(error.message||'Không tải được tên khách hàng.',true);}
}
function showConfigModal(){const modal=document.getElementById('configModal');if(modal)modal.classList.remove('hidden');loadConfig();}
function closeConfigModal(){const modal=document.getElementById('configModal');if(modal)modal.classList.add('hidden');}
document.addEventListener('DOMContentLoaded',()=>{
    document.getElementById('configBtn')?.addEventListener('click',showConfigModal);
    document.getElementById('closeConfigModal')?.addEventListener('click',closeConfigModal);
    document.getElementById('accountSelect')?.addEventListener('change',()=>{
        const select=document.getElementById('accountSelect'),header=document.getElementById('customerHeader');
        if(header)header.textContent=select.selectedOptions[0]?.dataset.customerName||select.value;
        if(!document.getElementById('configModal').classList.contains('hidden'))loadConfig();
    });
    document.getElementById('configForm').onsubmit=async event=>{
        event.preventDefault();const account=nameAccount,input=document.getElementById('customer_name'),save=document.getElementById('customerNameSave');
        if(!account||input.disabled)return;save.disabled=true;input.disabled=true;
        try{
            const data=await nameAPI('POST',account,{name:input.value,expected_custom_name:expectedName});
            applyCustomerName(data);
            if(account===nameAccount){expectedName=data.custom_name;input.value=data.custom_name||data.official_name||'';showMsg(`Đã lưu tên cho mã ${account}.`);}
        }catch(error){showMsg(error.message||'Chưa lưu được tên khách hàng.',true);}
        finally{if(account===nameAccount){save.disabled=false;input.disabled=false;}}
    };
});
