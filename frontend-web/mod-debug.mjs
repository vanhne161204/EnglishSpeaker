import puppeteer from "puppeteer-core";
const OWNER=process.argv[2], RID=process.argv[3];
const URL="http://localhost:8080/rooms/"+RID;
const browser=await puppeteer.launch({executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe",headless:"new",args:["--no-sandbox"]});
try {
  const owner=await browser.newPage();
  owner.on("pageerror",e=>console.log("PAGEERR:",e.message));
  await owner.goto(URL,{waitUntil:"networkidle2",timeout:30000});
  await owner.evaluate((id)=>localStorage.setItem("et_user",JSON.stringify({id,display_name:"HostUser",level:null,interests:null,phone:null,mode:"normal"})),OWNER);
  await owner.reload({waitUntil:"networkidle2"});
  await owner.waitForFunction(()=>/in the room/i.test(document.body.innerText),{timeout:12000});
  const member=await browser.newPage();
  await member.goto(URL,{waitUntil:"networkidle2",timeout:30000});
  await member.waitForFunction(()=>/in the room/i.test(document.body.innerText),{timeout:12000});
  await new Promise(r=>setTimeout(r,3000));
  const info = await owner.evaluate(()=>({
    storedId: JSON.parse(localStorage.getItem("et_user")||"{}").id,
    memberRows: [...document.querySelectorAll("li")].map(li=>li.innerText.replace(/\n/g," ").slice(0,50)),
    kickButtons: [...document.querySelectorAll("button")].filter(b=>b.innerText.trim()==="Kick").length,
  }));
  console.log("owner storedId:", info.storedId);
  console.log("owner expected:", OWNER, "match:", info.storedId===OWNER);
  console.log("owner member rows:");
  info.memberRows.forEach(r=>console.log("   -",r));
  console.log("owner kick buttons:", info.kickButtons);
} catch(e){ console.log("FAIL "+e.message); }
finally { await browser.process()?.kill("SIGKILL"); process.exit(0); }
