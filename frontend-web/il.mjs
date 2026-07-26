import puppeteer from "puppeteer-core";
const browser=await puppeteer.launch({executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe",headless:"new",args:["--use-fake-ui-for-media-stream","--use-fake-device-for-media-stream","--autoplay-policy=no-user-gesture-required","--no-sandbox"]});
const page=await browser.newPage();
const click=async(t)=>page.evaluate((n)=>{const b=[...document.querySelectorAll("button,a")].find(x=>x.innerText.includes(n));if(b){b.click();return true}return false},t);
const mic=()=>page.evaluate(()=>{const b=[...document.querySelectorAll("button")].map(x=>x.innerText.trim());return b.find(t=>/Mic on|Mic off|Paused for AI/.test(t))||"(none)"});
try{
  await page.goto(process.argv[2],{waitUntil:"networkidle2",timeout:30000});
  await page.waitForFunction(()=>/join call/i.test(document.body.innerText),{timeout:12000});
  await click("Join call");
  await page.waitForFunction(()=>/mic on/i.test(document.body.innerText),{timeout:8000});
  console.log("join:",await mic());
  await click("Start talking");
  await page.waitForFunction(()=>/paused for ai/i.test(document.body.innerText),{timeout:6000});
  console.log("AI start:",await mic());
  await click("Stop");
  await new Promise(r=>setTimeout(r,700));
  console.log("AI stop:",await mic());
}catch(e){console.log("FAIL "+e.message)}
finally{await page.browser().process()?.kill("SIGKILL");process.exit(0)}
