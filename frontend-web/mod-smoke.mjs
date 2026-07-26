import puppeteer from "puppeteer-core";
const OWNER=process.argv[2], RID=process.argv[3];
const URL="http://localhost:8080/rooms/"+RID;
const browser=await puppeteer.launch({executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe",headless:"new",args:["--no-sandbox"]});
const hasKick=(p)=>p.evaluate(()=>[...document.querySelectorAll("button")].some(b=>b.innerText.trim()==="Kick"));
try {
  // Owner in default context with injected owner identity
  const owner=await browser.newPage();
  await owner.goto(URL,{waitUntil:"networkidle2",timeout:30000});
  await owner.evaluate((id)=>localStorage.setItem("et_user",JSON.stringify({id,display_name:"HostUser",level:null,interests:null,phone:null,mode:"normal"})),OWNER);
  await owner.reload({waitUntil:"networkidle2"});
  await owner.waitForFunction(()=>/in the room/i.test(document.body.innerText),{timeout:12000});
  // Member in an ISOLATED context (own localStorage -> fresh user)
  const ctx=await browser.createBrowserContext();
  const member=await ctx.newPage();
  await member.goto(URL,{waitUntil:"networkidle2",timeout:30000});
  await member.waitForFunction(()=>/in the room/i.test(document.body.innerText),{timeout:12000});
  // owner should now see the member row with a Kick button
  await owner.waitForFunction(()=>[...document.querySelectorAll("button")].some(b=>b.innerText.trim()==="Kick"),{timeout:12000}).catch(()=>{});
  console.log("owner sees Kick buttons:", await hasKick(owner), "(expect true)");
  console.log("member sees Kick buttons:", await hasKick(member), "(expect false)");
  const ownerRows = await owner.evaluate(()=>[...document.querySelectorAll("li")].map(li=>li.innerText.replace(/\n/g," ").slice(0,40)).filter(t=>/you|guest|user/i.test(t)));
  console.log("owner member rows:", JSON.stringify(ownerRows));
  // Owner mutes the member first
  await owner.evaluate(()=>{const b=[...document.querySelectorAll("button")].find(x=>/Off/.test(x.innerText)&&x.innerText.includes("🔇")); if(b)b.click();});
  await new Promise(r=>setTimeout(r,800));
  console.log("member got host-mute notice:", await member.evaluate(()=>/muted your microphone/i.test(document.body.innerText)));
  // Owner kicks the member
  await owner.evaluate(()=>{const b=[...document.querySelectorAll("button")].find(x=>x.innerText.trim()==="Kick"); if(b)b.click();});
  await new Promise(r=>setTimeout(r,2200));
  console.log("member URL after kick:", member.url().replace("http://localhost:8080",""), "(expect /rooms)");
  console.log("member saw removed notice:", await member.evaluate(()=>/removed from this room/i.test(document.body.innerText)));
} catch(e){ console.log("FAIL "+e.message); }
finally { await browser.process()?.kill("SIGKILL"); process.exit(0); }
