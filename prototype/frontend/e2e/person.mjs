// Asks for a person with every AI model switched off, then checks the back office. Spends no AI quota.
// Needs an API started with empty GROQ_API_KEY and GEMINI_API_KEY, and a web app pointing at it.
//   BASE_URL=http://localhost:3000 node e2e/person.mjs [output-folder]
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const OUT = process.argv[2] ?? "e2e/screenshots";
const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const MOBILE = "9876543210";
const MASKED = "98******10";
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ channel: "msedge", headless: true });
const problems = [];

function watch(page) {
  page.on("pageerror", (error) => problems.push(`page error: ${error.message}`));
  page.on("response", (response) => {
    if (response.status() >= 500) problems.push(`HTTP ${response.status()}: ${response.url()}`);
  });
}

function expect(condition, message) {
  console.log(`${condition ? "ok  " : "FAIL"} ${message}`);
  if (!condition) problems.push(message);
}

async function phone(language, startLabel) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  const page = await context.newPage();
  watch(page);
  await page.goto(BASE);
  await page.getByRole("button", { name: language, exact: true }).click();
  await page.getByRole("button", { name: startLabel, exact: true }).click();
  await page.locator("input[maxlength='1000']").waitFor();
  await page.waitForTimeout(800);
  return { context, page };
}

async function sendMessage(page, text) {
  await page.locator("input[maxlength='1000']").fill(text);
  await page.locator("form button[type=submit]").first().click();
}

const backOffice = await browser.newContext({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1.5 });
const office = await backOffice.newPage();
watch(office);

async function openBackOffice() {
  const response = office.waitForResponse((r) => r.url().includes("/backoffice/queue"));
  await office.goto(`${BASE}/backoffice`);
  const body = await (await response).text();
  await office.getByRole("table").waitFor();
  await office.waitForTimeout(300);
  return body;
}

const liveRows = () => office.locator("tbody tr").filter({ hasText: "· Advisor" });
// Requests from an earlier run stay until the API restarts, so everything is counted from here.
const before = JSON.parse(await openBackOffice());

// --- Hindi: ask in words, before any plan, then finish the plan with the request still open ---
{
  const { context, page } = await phone("हिन्दी", "शुरू करें");
  const label = "किसी व्यक्ति से बात करें";
  expect(await page.getByRole("button", { name: label }).count() === 1, "the button is always in the header");
  expect(await page.evaluate(() => document.documentElement.scrollWidth) <= 390, "the header fits on a phone");

  await sendMessage(page, "मुझे किसी से बात करनी है");
  await page.getByText("हमारी टीम आपको कॉल करेगी").waitFor({ timeout: 20_000 });
  await page.getByText("सरल सवाल").waitFor();
  expect(await page.getByRole("button", { name: label }).count() === 2, "asking in the chat also shows the button there");
  await page.screenshot({ path: `${OUT}/22_person_offer_hindi.png` });

  await page.getByRole("button", { name: label }).last().click();
  const dialog = page.getByRole("dialog");
  await dialog.waitFor();
  const send = dialog.getByRole("button", { name: "कॉल का अनुरोध भेजें" });
  expect(await send.isDisabled(), "the form can't be sent before there's a number and consent");
  await dialog.locator("input[type=tel]").fill("12345");
  expect(await send.isDisabled(), "a number alone isn't enough: consent is needed");
  await dialog.locator("input[type=checkbox]").check();
  await page.screenshot({ path: `${OUT}/23_person_form_hindi.png` });
  await send.click();
  await dialog.getByText("10 अंकों").waitFor();
  expect(true, "a bad number gets a message in Hindi");

  await dialog.locator("input[type=tel]").fill(MOBILE);
  await send.click();
  await dialog.getByText(MASKED).waitFor();
  await page.screenshot({ path: `${OUT}/24_person_sent_hindi.png` });
  expect(!(await dialog.innerText()).includes(MOBILE), "the owner sees the number masked after sending");
  await dialog.getByRole("button", { name: "बंद करें" }).click();
  expect(await page.getByRole("button", { name: "कॉल का अनुरोध भेजा" }).isVisible(), "the header shows the call was requested");

  let queue = JSON.parse(await openBackOffice());
  expect(queue.live === before.live + 1, "the request is in the queue straight away");
  expect((await liveRows().first().innerText()).includes("New"), "before a plan the score says New");
  expect((await liveRows().first().innerText()).includes("Asked before getting a plan"), "the reason says they asked before a plan");

  await page.getByRole("button", { name: "दुकान या स्टोर" }).click();
  await page.getByRole("button", { name: "3-4", exact: true }).click();
  await page.getByRole("button", { name: "1", exact: true }).click();
  await page.getByRole("button", { name: "Nagpur", exact: true }).click();
  await page.getByRole("button", { name: "GST नहीं है" }).click();
  await page.getByRole("button", { name: "बिलिंग और UPI" }).click();
  await page.getByRole("button", { name: "CCTV", exact: true }).click();
  await page.getByRole("button", { name: "हो गया" }).click();
  await page.getByRole("button", { name: "मेरी कीमत देखें" }).waitFor({ timeout: 15_000 });

  const raw = await openBackOffice();
  queue = JSON.parse(raw);
  const row = await liveRows().first().innerText();
  await office.screenshot({ path: `${OUT}/25_backoffice_live.png` });
  expect(!raw.includes(MOBILE), "the full number isn't in the API response");
  expect(!(await office.content()).includes(MOBILE), "the full number isn't in the page");
  expect(row.includes(MASKED), "the row shows the masked number");
  expect(/\d+%/.test(row), "with a plan, the row shows a percentage");
  expect(row.includes("Local partner"), "no GST goes to a local partner, by the same rule as other leads");
  expect(row.includes("Wants to talk before buying") && row.includes("Reached: Plan"), "the reason and stage follow how far they got");
  expect(row.includes("₹2,545"), "the next step names the plan's price");
  expect(queue.by_owner["Local partner"] === before.by_owner["Local partner"] + 1, "the tab count includes the live lead");
  expect(await office.getByText("Last quarter's leads", { exact: true }).isVisible(), "live and past leads are labelled apart");

  await page.getByRole("button", { name: "कॉल का अनुरोध भेजा" }).click();
  await dialog.getByRole("button", { name: "यह अनुरोध रद्द करें" }).click();
  await dialog.getByText("आपका नंबर मिटा दिया गया").waitFor();
  expect(JSON.parse(await openBackOffice()).live === before.live, "cancelling removes the lead");
  expect(await office.getByText("got a plan but left no number").isVisible(), "a chat with a plan and no number is only counted");
  await context.close();
}

// --- English: stuck at documents, then the order closes the lead ------------------------------
{
  const { context, page } = await phone("English", "Start");
  await sendMessage(page, "hello");
  await page.getByText("Guided mode").waitFor({ timeout: 20_000 });
  for (const option of ["Shop or store", "3-4", "1", "Nagpur", "No GST", "Done"]) {
    await page.getByRole("button", { name: option, exact: true }).click();
  }
  await page.getByRole("button", { name: "See my price" }).click();
  await page.getByRole("button", { name: "Continue to documents" }).click();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Agree and continue" }).click();

  const specimen = page.getByRole("combobox");
  await specimen.selectOption("K04");
  await page.getByRole("button", { name: "Check my documents" }).waitFor();
  await page.waitForFunction(() => !document.querySelector("main, body")?.innerText.includes("Reading…"), null, { timeout: 90_000 });
  await page.getByRole("button", { name: "Check my documents" }).click();
  await page.getByText("Please fix the items below").waitFor({ timeout: 30_000 });

  await page.getByRole("button", { name: "Talk to a person" }).last().click();
  const dialog = page.getByRole("dialog");
  await dialog.locator("input[type=tel]").fill(`+91 ${MOBILE}`);
  await dialog.locator("input[type=checkbox]").check();
  await dialog.getByRole("button", { name: "Ask for a call" }).click();
  await dialog.getByText(MASKED).waitFor();
  await dialog.getByRole("button", { name: "Close" }).click();

  await openBackOffice();
  const row = await liveRows().first().innerText();
  expect(row.includes("Documents need fixing") && row.includes("Reached: Documents"), "a blocked KYC shows as documents needing fixing");

  await specimen.selectOption("K03");
  await page.waitForFunction(() => !document.querySelector("main, body")?.innerText.includes("Reading…"), null, { timeout: 90_000 });
  await page.getByRole("button", { name: "Check my documents" }).click();
  await page.getByRole("button", { name: "E-sign and pay" }).click({ timeout: 30_000 });
  await page.getByRole("button", { name: "Sign and place order" }).click();
  await page.getByText("Simulate next step").waitFor({ timeout: 15_000 });
  expect(await page.getByRole("button", { name: "Talk to a person" }).count() === 0, "after ordering, the header button goes away");
  expect(JSON.parse(await openBackOffice()).live === before.live, "placing the order removes the lead");
  await context.close();
}

// --- Tamil and Kannada: the form is translated -------------------------------------------------
for (const [language, start, button, send, shot] of [
  ["தமிழ்", "தொடங்கு", "ஒருவரிடம் பேசுங்கள்", "அழைப்பு கோருங்கள்", "26_person_form_tamil"],
  ["ಕನ್ನಡ", "ಪ್ರಾರಂಭಿಸಿ", "ವ್ಯಕ್ತಿಯೊಂದಿಗೆ ಮಾತನಾಡಿ", "ಕರೆಗೆ ವಿನಂತಿಸಿ", "27_person_form_kannada"],
]) {
  const { context, page } = await phone(language, start);
  await page.getByRole("button", { name: button }).click();
  await page.getByRole("dialog").getByRole("button", { name: send }).waitFor();
  await page.screenshot({ path: `${OUT}/${shot}.png` });
  expect(await page.evaluate(() => document.documentElement.scrollWidth) <= 390, `the ${language} form fits on a phone`);
  await context.close();
}

await browser.close();
console.log(problems.length ? `\nPROBLEMS:\n${[...new Set(problems)].join("\n")}` : "\nNo problems found.");
process.exitCode = problems.length ? 1 : 0;
