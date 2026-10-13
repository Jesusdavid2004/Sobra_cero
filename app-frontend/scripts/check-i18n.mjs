import { readFileSync } from "node:fs";

const locales = ["en", "es"];
const messages = Object.fromEntries(
  locales.map((locale) => [
    locale,
    JSON.parse(readFileSync(new URL(`../i18n/${locale}.json`, import.meta.url), "utf8")),
  ]),
);
const failures = [];
const englishKeys = Object.keys(messages.en).sort();
const spanishKeys = Object.keys(messages.es).sort();

for (const key of englishKeys) {
  if (typeof messages.en[key] !== "string" || typeof messages.es[key] !== "string") {
    failures.push(`${key}: every message must be a string`);
    continue;
  }

  const placeholders = (message) =>
    [...message.matchAll(/\{([A-Za-z][A-Za-z0-9_]*)\}/g)].map((match) => match[1]).sort();
  if (
    JSON.stringify(placeholders(messages.en[key])) !==
    JSON.stringify(placeholders(messages.es[key]))
  ) {
    failures.push(`${key}: ICU placeholders differ between en and es`);
  }
}

for (const key of spanishKeys) {
  if (!Object.hasOwn(messages.en, key)) failures.push(`${key}: missing from en`);
}
for (const key of englishKeys) {
  if (!Object.hasOwn(messages.es, key)) failures.push(`${key}: missing from es`);
}

if (failures.length) {
  console.error(`i18n:check failed:\n${failures.map((failure) => `- ${failure}`).join("\n")}`);
  process.exitCode = 1;
} else {
  console.log(`i18n:check passed (${englishKeys.length} messages in en and es)`);
}
