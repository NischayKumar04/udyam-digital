# Competitive analysis: raw material for slide 6

Based on public pages read on 2 Nov 2026. "Not shown" means we didn't see it on the pages we read, not that it doesn't exist. We read sales and pricing pages and did not complete any sign-up. Prices exclude GST unless noted. Accel is the case's fictional operator, so its figures come from `product_catalogue.csv` and our pricing rule.

## Who else serves these businesses

**Telecom operators selling bundles**

| Player | Entry offer | Included | How you buy | Time to activate |
|---|---|---|---|---|
| **Jio** Business Broadband Max | "Max 801": 100 Mbps. Press reports ₹801 + GST; Jio's page shows no amount we could read. No setup fee | 1,200 GB a month, then 1 Mbps. 5 JioAttendance, 1 JioMeet, 1 JioGate. No static IP by default. Best-effort speed, upload lower than download | "Request a callback"; "Buy Plan" buttons whose target we couldn't confirm | Not shown |
| **Tata Tele** SmartOffice | No price shown; listed for 7 metros only | Unlimited data, SLA, voice line on plans above 100 Mbps, Microsoft 365 tools, WatchGuard endpoint and Cisco DNS security | Enquiry form or callback. 6 or 12-month contract tied to the free router | Not shown |
| **Vi** Business | Business Plus Postpaid; TelecomTalk reports 5G business plans from ₹349. No price on Vi's own page | Mobile-led: data rollover, mobile security, Google Workspace resale, consolidated billing. No small-business fibre found | Assisted KYC: a rep calls within 48 hours | "Within hours once documentation is complete" |

**Internet providers**

| Player | Entry offer | Included | How you buy | Time to activate |
|---|---|---|---|---|
| **ACT** business | 1 Gbps from ₹5,999 a month | 10 TB, free static IP, Wi-Fi 6 managed router, antivirus, guest Wi-Fi, SIM backup. No mobile or cloud | "Get Now" flow with an "Online KYC" option, or callback | Not shown |
| **Local ISPs** | No public data | Connectivity only | Local reseller | Not shown |

**Digital-first, single-product players**

| Player | What it sells | Published price | How you buy |
|---|---|---|---|
| **AiSensy** | WhatsApp API | Free plan available (figures not readable). Marketing message ₹1.09, service ₹0.145. Virtual number needs GST or MSME registration | Self-serve sign-up |
| **Interakt** (footer names Jio Haptik) | WhatsApp API | Growth ₹2,799/month, Advanced ₹3,799/month | Free trial; "Assisted" onboarding on these tiers |
| **WATI** | WhatsApp API | Growth ₹2,699/month billed quarterly | 7-day free trial, needs Meta Business Manager admin access |
| **Google Workspace** | Email and documents | Base ₹99/user/month (up to 20 users), Starter ₹270/user/month | Self-serve 14-day trial |
| **MyOperator** | Cloud calling | Sedan ₹5,000/month for 10 users, billed yearly; toll-free from ₹500/month | Free trial |
| **Petpooja** | Restaurant POS | Base ₹12,000 (billing period not stated) | Book a demo |

## Price check: Accel against the published alternative

| Need | Accel (catalogue range per month) | Alternative | Who's cheaper |
|---|---|---|---|
| 100 Mbps internet | ₹999-1,199, unlimited data | Jio Max 801, reported ₹801, 1,200 GB then 1 Mbps | **Jio on headline price**; Accel on unlimited data |
| 1 Gbps internet | ₹3,999-4,499 | ACT ₹5,999, with static IP, router and antivirus included | Accel on price; ACT includes more |
| WhatsApp API | ₹999-1,499 | WATI ₹2,699, Interakt ₹2,799 | **Accel**, though they include chatbots and AI credits. AiSensy has a free plan |
| Business email, per user | ₹125-150 | Google Base ₹99, Starter ₹270 | Google Base is cheaper; Accel beats Starter |
| Cloud calling | ₹1,000-1,500 per channel | MyOperator ₹5,000 for 10 users | Depends on size: Accel for up to about 3 channels |
| Toll-free number | ₹1,500-2,000 | MyOperator from ₹500, on top of a plan | MyOperator on the add-on |
| POS and billing | ₹599-899 per counter + ₹2,500 setup | Petpooja ₹12,000, period not stated | Can't compare until the period is known |

Accel is not the cheapest on every line, and we shouldn't claim it is. The argument is one bill, one sign-up and the right bundle first time.

## The buying journey

| Capability | Jio | Tata Tele | Vi | ACT | Single-product tools | Accel (our design) |
|---|---|---|---|---|---|---|
| Connectivity, mobile, cloud, security and IoT from one seller | Partial | Partial | Partial | No | No | **Yes, 25 products** |
| Price visible before talking to sales | Not readable | No | No | Yes | Yes | **Yes** |
| Recommendation without a salesperson | Not shown | Not shown | Not shown | Not shown | n/a | **Yes** |
| Buy without a call | Unclear | No | No | Partly | Yes | **Yes** |
| KYC by instant registry lookup | Not shown | Not shown | No (assisted) | Online KYC, details not shown | n/a | **Yes** |
| Buying journey in Indian languages | Not shown | Not shown | Not shown | Callback preference only | Not shown | **Yes** |
| Activation date at quote, and a tracker | Not shown | Not shown | Hours after documents; no tracker shown | Not shown | Instant for software | **Yes** |

## What our own leads say about competition

| Current provider | Leads | Activated | Conversion |
|---|---|---|---|
| Accel (mobile only) | 1,505 | 139 | 9.2% |
| Accel | 385 | 35 | 9.1% |
| Competitor B | 744 | 55 | 7.4% |
| Competitor A | 1,200 | 78 | 6.5% |
| Local ISP | 1,042 | 56 | 5.4% |

- 325 leads dropped as "Locked in with current provider", and 207 as "Competitor offered cheaper plan".
- Existing Accel mobile customers are the largest group and convert best, so they are the cheapest place to start.

## Where we win, where we lose, and what we do about it

**We win on:**
- One sign-up and one bill across 25 products, where rivals cover part of the stack.
- Advice and a price in one sitting. Tata Tele, Vi and Jio all route through a callback or an assisted step.
- The buying journey in the owner's language, which we didn't see on any rival's pages.
- Getting it right first time: 0 rule breaks across 5,000 replayed leads.

**We lose on:**
- **Headline price.** Jio's reported ₹801 undercuts our ₹999 floor for 100 Mbps. Don't compete on this line: compare unlimited data with a 1,200 GB cap, and the whole bundle with buying separately.
- **Depth in a single product.** WhatsApp tools offer chatbots and CRM that our starter doesn't, and Google Base is cheaper for email only. Sell the bundle, and integrate rather than out-build.
- **Copying risk.** Jio has the reach, and Interakt's footer names Jio Haptik Technologies, so it already has a foot in AI chat for business. The journey can be copied in time. Partner reach, registry-backed KYC data and the base of existing mobile customers are harder to copy.
- **Commitment.** Rivals offer free trials, while our fibre needs a 12-month contract. Answer with AirFiber on 6 months and mobile lines month to month.

## Sources

- Jio Max 801 details: [TelecomTalk](https://telecomtalk.info/?p=1005076), [The Tech Outlook](https://www.thetechoutlook.com/telecom/reliance-jiobusiness-broadband-max-801-plan-bundles-connectivity-and-workplace-tools-for-small-businesses/)
- Jio pricing reports: [PC-Tablet](https://pc-tablet.com/?p=72921)
- Jio official: [Business](https://www.jio.com/business/), [Business Broadband Max](https://www.jio.com/business/services/connectivity/business-broadband-max/), [Jio article](https://www.jio.com/business/article/a-smarter-way-to-scale-with-business-broadband-max/)
- Tata Tele: [SmartOffice Business Broadband](https://www.tatatelebusiness.com/data-services/business-broadband/)
- Vi: [Vi Business](https://www.myvi.in/business), [Corporate postpaid](https://www.myvi.in/business/enterprise-mobility/corporate-postpaid-plans), [TelecomTalk on 5G plans](https://telecomtalk.info/vodafone-idea-5g-postpaid-plans-for-business/992802/)
- ACT: [Business plans](https://www.actcorp.in/enterprise-business/eb-plans), [Corporate broadband](https://www.actcorp.in/enterprise-business/corporate-broadband)
- WhatsApp tools: [AiSensy](https://aisensy.com/pricing), [Interakt](https://www.interakt.shop/pricing/), [WATI](https://www.wati.io/pricing/)
- Others: [Google Workspace India](https://workspace.google.com/intl/en_in/pricing), [MyOperator](https://myoperator.com/pricing), [Petpooja](https://www.petpooja.com/pricing)
