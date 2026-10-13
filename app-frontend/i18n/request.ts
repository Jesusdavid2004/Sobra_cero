import { hasLocale } from "next-intl";
import { getRequestConfig } from "next-intl/server";

import en from "./en.json";
import es from "./es.json";
import { routing } from "./routing";

const messages = { en, es };

export default getRequestConfig(async ({ requestLocale }) => {
  const requestedLocale = await requestLocale;
  const locale = hasLocale(routing.locales, requestedLocale)
    ? requestedLocale
    : routing.defaultLocale;

  return { locale, messages: messages[locale] };
});
