// Walks the whole owner journey in a real browser and saves screenshots.
// Needs the API and web app running. Run from prototype/frontend:
//   node e2e/journey.mjs [output-folder]
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const OUT = process.argv[2] ?? "e2e/screenshots";
const BASE = process.env.BASE_URL ?? "http://localhost:3000";
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ channel: "msedge", headless: true });
const problems = [];

function watch(page) {
  page.on("pageerror", (error) => problems.push(`page error: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error") problems.push(`console: ${message.text()}`);
  });
  page.on("response", (response) => {
    if (response.status() >= 500) problems.push(`HTTP ${response.status()}: ${response.url()}`);
  });
}

async function phone() {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  const page = await context.newPage();
  watch(page);
  return page;
}

const shot = (page, name) => page.screenshot({ path: `${OUT}/${name}.png` });

async function chatToPlan(page, language, message, seePrice) {
  await page.goto(BASE);
  await page.getByRole("button", { name: language, exact: true }).click();
  await page.getByRole("button", { name: /^(Start|शुरू करें|தொடங்கு|ಪ್ರಾರಂಭಿಸಿ)$/ }).click();
  await page.locator("input[maxlength='1000']").waitFor();
  await page.waitForTimeout(800);
  await page.locator("input[maxlength='1000']").fill(message);
  await page.locator("form button[type=submit]").click();
  await page.getByRole("button", { name: seePrice }).waitFor({ timeout: 60_000 });
  await page.waitForTimeout(500);
}

// --- Main journey, in Hindi ------------------------------------------------------------
{
  const page = await phone();
  await page.goto(BASE);
  await page.getByRole("button", { name: "हिन्दी", exact: true }).click();
  await page.waitForTimeout(300);
  await shot(page, "01_home_hindi");

  await chatToPlan(page, "हिन्दी", "नागपुर में मेरी किराना दुकान है, 2 लोग काम करते हैं, एक ही दुकान है, GST नहीं है। बिलिंग और CCTV चाहिए।", "मेरी कीमत देखें");
  await shot(page, "02_advisor_hindi");
  console.log("Advisor reply:", (await page.locator("p.whitespace-pre-wrap").last().innerText()).slice(0, 200));

  await page.getByRole("button", { name: "मेरी कीमत देखें" }).click();
  await page.waitForTimeout(800);
  await shot(page, "03_quote_hindi");
  const before = await page.locator("p.text-2xl:visible").first().innerText();
  await page.getByRole("switch", { name: "Secure Wi-Fi with Guest Network" }).click();
  await page.waitForTimeout(800);
  const after = await page.locator("p.text-2xl:visible").first().innerText();
  console.log(`Toggle add-on: ${before} -> ${after}`);
  if (before === after) problems.push("toggling an add-on didn't change the price");
  await page.getByRole("switch", { name: "Secure Wi-Fi with Guest Network" }).click();
  await page.waitForTimeout(600);

  await page.getByRole("button", { name: "दस्तावेज़ों पर जाएँ" }).click();
  await page.getByRole("heading", { name: "दस्तावेज़ पढ़ने से पहले" }).waitFor();
  await shot(page, "04_consent_hindi");

  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "सहमत होकर आगे बढ़ें" }).click();
  await page.getByRole("heading", { name: "आपके दस्तावेज़" }).waitFor();
  await page.waitForTimeout(600);
  await shot(page, "05_documents_no_gst_hindi");

  await page.locator("select").selectOption("K06");
  await page.waitForTimeout(500);
  await page.waitForFunction(() => !document.body.innerText.includes("पढ़ रहे हैं"), null, { timeout: 90_000 });
  await page.getByRole("button", { name: "दस्तावेज़ जाँचें" }).click();
  await page.getByText("हमारी टीम इसकी जाँच करेगी", { exact: true }).waitFor({ timeout: 30_000 });
  await page.locator("section[aria-live=polite]").scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
  await shot(page, "05b_kyc_altered_gstin_hindi");

  await page.locator("select").selectOption("K03");
  await page.waitForTimeout(500);
  await page.getByRole("button", { name: "दस्तावेज़ जाँचें" }).waitFor();
  await page.waitForFunction(() => !document.body.innerText.includes("पढ़ रहे हैं"), null, { timeout: 90_000 });
  await page.getByRole("button", { name: "दस्तावेज़ जाँचें" }).click();
  await page.getByText("सब सत्यापित").waitFor({ timeout: 30_000 });
  await page.getByText("सब सत्यापित").scrollIntoViewIfNeeded();
  await shot(page, "06_verified_hindi");

  await page.getByRole("button", { name: "ई-साइन और भुगतान" }).click();
  await page.getByRole("button", { name: "हस्ताक्षर करके ऑर्डर करें" }).click();
  await page.getByText(/ऑर्डर UD-/).waitFor({ timeout: 15_000 });
  await page.waitForTimeout(500);
  await shot(page, "07_tracker_hindi");
  await page.getByRole("button", { name: /अगला कदम दिखाएँ/ }).click();
  await page.waitForTimeout(500);
  await page.getByRole("button", { name: /अगला कदम दिखाएँ/ }).click();
  await page.waitForTimeout(500);
  await shot(page, "08_tracker_progress_hindi");
  console.log("Tracker heading:", await page.locator("h1").innerText());
  await page.context().close();
}

// --- The same journey in Tamil ----------------------------------------------------------
{
  const page = await phone();
  await chatToPlan(page, "தமிழ்", "சென்னையில் என் பல் மருத்துவமனை உள்ளது. 14 பேர் வேலை செய்கிறார்கள், ஒரே இடம், GST உள்ளது.", "என் விலையைப் பார்");
  await shot(page, "16_advisor_tamil");
  await page.getByRole("button", { name: "என் விலையைப் பார்" }).click();
  await page.waitForTimeout(800);
  await shot(page, "17_quote_tamil");
  await page.getByRole("button", { name: "ஆவணங்களுக்குச் செல்" }).click();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "ஒப்புக்கொண்டு தொடர்" }).click();
  await page.getByRole("heading", { name: "உங்கள் ஆவணங்கள்" }).waitFor();
  await page.locator("select").selectOption("K11");
  await page.waitForTimeout(500);
  await page.waitForFunction(() => !document.body.innerText.includes("படிக்கிறது"), null, { timeout: 90_000 });
  await page.getByRole("button", { name: "என் ஆவணங்களைச் சரிபார்" }).click();
  await page.getByText("கீழே உள்ளவற்றைச் சரிசெய்யுங்கள்", { exact: true }).waitFor({ timeout: 30_000 });
  await page.locator("section[aria-live=polite]").scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
  await shot(page, "18_kyc_old_bill_tamil");
  await page.locator("select").selectOption("K03");
  await page.waitForTimeout(500);
  await page.waitForFunction(() => !document.body.innerText.includes("படிக்கிறது"), null, { timeout: 90_000 });
  await page.getByRole("button", { name: "என் ஆவணங்களைச் சரிபார்" }).click();
  await page.getByText("அனைத்தும் சரிபார்க்கப்பட்டது", { exact: true }).waitFor({ timeout: 30_000 });
  await page.getByRole("button", { name: "மின்-கையொப்பம் மற்றும் கட்டணம்" }).click();
  await page.getByRole("button", { name: "கையொப்பமிட்டு ஆர்டர் செய்" }).click();
  await page.getByText(/ஆர்டர் UD-/).waitFor({ timeout: 15_000 });
  await page.getByRole("button", { name: /அடுத்த கட்டத்தைக் காட்டு/ }).click();
  await page.waitForTimeout(500);
  await shot(page, "19_tracker_tamil");
  await page.context().close();
}

// --- KYC catching planted problems, in English ------------------------------------------
{
  const page = await phone();
  await chatToPlan(page, "English", "We're a dental clinic in Kochi with 14 staff, one site, and we have GST registration.", "See my price");
  await shot(page, "09_advisor_english");
  await page.getByRole("button", { name: "See my price" }).click();
  await page.waitForTimeout(800);
  await shot(page, "10_quote_english");
  await page.getByRole("button", { name: "Continue to documents" }).click();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Agree and continue" }).click();
  await page.getByRole("heading", { name: "Your documents" }).waitFor();

  for (const [sample, file] of [["K06", "11_kyc_altered_gstin"], ["K11", "12_kyc_old_bill"], ["K04", "13_kyc_blurred"], ["K01", "14_kyc_cancelled_gstin"]]) {
    await page.locator("select").selectOption(sample);
    await page.waitForTimeout(500);
    await page.waitForFunction(() => !document.body.innerText.includes("Reading…"), null, { timeout: 90_000 });
    await page.getByRole("button", { name: "Check my documents" }).click();
    await page.locator("section[aria-live=polite] p").first().waitFor({ timeout: 30_000 });
    await page.waitForTimeout(300);
    await page.locator("section[aria-live=polite]").scrollIntoViewIfNeeded();
    await shot(page, file);
    console.log(`${sample}:`, await page.locator("section[aria-live=polite] p").first().innerText());
  }
  await page.context().close();
}

// --- Back office on a laptop screen -----------------------------------------------------
{
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 2 });
  const page = await context.newPage();
  watch(page);
  await page.goto(`${BASE}/backoffice`);
  await page.getByRole("table").waitFor();
  await page.waitForTimeout(400);
  await shot(page, "15_backoffice");
  await context.close();
}

await browser.close();
console.log(problems.length ? `\nPROBLEMS:\n${problems.join("\n")}` : "\nNo browser errors.");
process.exitCode = problems.length ? 1 : 0;
