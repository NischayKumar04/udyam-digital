// Walks the advisor with every AI model switched off, to prove the journey survives.
// Needs an API started with empty GROQ_API_KEY and GEMINI_API_KEY, and a web app pointing at it.
//   BASE_URL=http://localhost:3001 node e2e/guided.mjs [output-folder]
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const OUT = process.argv[2] ?? "e2e/screenshots";
const BASE = process.env.BASE_URL ?? "http://localhost:3001";
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ channel: "msedge", headless: true });
const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
const page = await context.newPage();
const problems = [];
page.on("pageerror", (error) => problems.push(`page error: ${error.message}`));
page.on("response", (response) => {
  if (response.status() >= 500) problems.push(`HTTP ${response.status()}: ${response.url()}`);
});

await page.goto(BASE);
await page.getByRole("button", { name: "हिन्दी", exact: true }).click();
await page.getByRole("button", { name: "शुरू करें" }).click();
const input = page.locator("input[maxlength='1000']");
await input.waitFor();
await page.waitForTimeout(800);
await input.fill("नमस्ते");
await page.locator("form button[type=submit]").click();

await page.getByText("सरल सवाल").waitFor({ timeout: 20_000 });
await page.getByRole("button", { name: "दुकान या स्टोर" }).click();
await page.getByRole("button", { name: "3-4", exact: true }).click();
await page.getByRole("button", { name: "1", exact: true }).click();
await page.getByRole("button", { name: "Nagpur", exact: true }).click();
await page.getByRole("button", { name: "GST नहीं है" }).click();
await page.getByRole("button", { name: "बिलिंग और UPI" }).click();
await page.getByRole("button", { name: "CCTV", exact: true }).click();
await page.waitForTimeout(300);
await page.screenshot({ path: `${OUT}/20_guided_needs_hindi.png` });
await page.getByRole("button", { name: "हो गया" }).click();
await page.getByRole("button", { name: "मेरी कीमत देखें" }).waitFor({ timeout: 15_000 });
await page.waitForTimeout(400);
await page.screenshot({ path: `${OUT}/21_guided_plan_hindi.png` });

const price = await page.locator("p.text-2xl:visible").first().innerText();
console.log("Guided plan price:", price);
if (!price.includes("2,545")) problems.push(`expected the same ₹2,545 plan the AI path gives, got ${price}`);

await browser.close();
console.log(problems.length ? `\nPROBLEMS:\n${problems.join("\n")}` : "No browser errors. The journey works with no AI at all.");
process.exitCode = problems.length ? 1 : 0;
