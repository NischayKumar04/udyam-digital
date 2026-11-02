"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { translator } from "@/lib/i18n";
import { Wordmark } from "./Journey";

export default function TrackLookup() {
  const router = useRouter();
  const [value, setValue] = useState("");
  const t = translator("English");

  return (
    <main className="mx-auto w-full max-w-md flex-1 px-5 py-8">
      <Wordmark />
      <h1 className="mt-10 text-2xl font-semibold tracking-tight">{t("track_link")}</h1>
      <form
        className="mt-4 flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (value.trim()) router.push(`/track/${encodeURIComponent(value.trim())}`);
        }}
      >
        <input
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder={t("enter_order")}
          aria-label={t("enter_order")}
          className="h-11 min-w-0 flex-1 rounded-xl border border-line bg-surface px-3 text-[15px] outline-none focus:border-muted"
        />
        <button type="submit" className="h-11 rounded-xl bg-accent px-4 text-sm font-semibold text-white">{t("find")}</button>
      </form>
    </main>
  );
}
