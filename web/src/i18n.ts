import es from "./i18n/es.json";
import hi from "./i18n/hi.json";
import fr from "./i18n/fr.json";
import pt from "./i18n/pt.json";
import de from "./i18n/de.json";
import ja from "./i18n/ja.json";
import it from "./i18n/it.json";

/**
 * Interface text in eight languages. The English text is the key; translations were written once,
 * ahead of time, by the Personalizer on Foundry and checked (`python -m app.ui_strings`), so nothing
 * here is translated live. A string with no translation shows in English.
 */
export type Lang = "en" | "es" | "hi" | "fr" | "pt" | "de" | "ja" | "it";

export const LANG_LABEL: Record<Lang, string> = {
  en: "English",
  es: "Español",
  fr: "Français",
  pt: "Português",
  de: "Deutsch",
  it: "Italiano",
  hi: "हिन्दी",
  ja: "日本語",
};

/** Browser speech locales, for when Azure AI Speech is unavailable. */
export const BROWSER_LANG: Record<Lang, string> = {
  en: "en-GB", es: "es-ES", hi: "hi-IN", fr: "fr-FR", pt: "pt-BR", de: "de-DE", ja: "ja-JP", it: "it-IT",
};

const TABLES: Partial<Record<Lang, Record<string, string>>> = { es, hi, fr, pt, de, ja, it };

let current: Lang = "en";

/** Set by the app shell on every render, before any component reads it. */
export function setLang(lang: Lang) {
  current = lang;
}

export function getLang(): Lang {
  return current;
}

/** The interface text in the fan's language. `{name}` placeholders are filled from `vars`. */
export function t(text: string, vars?: Record<string, string | number>): string {
  const table = TABLES[current];
  let out = (table && table[text]) || text;
  if (vars) for (const [k, v] of Object.entries(vars)) out = out.split(`{${k}}`).join(String(v));
  return out;
}

/** Marks text for translation where it is defined (labels in maps); translate it with t() where it is shown. */
export const tx = (text: string) => text;

/** A label map whose values are shown in the fan's language: each read translates, so every place
 * that shows the map follows the language switch. */
export function labels<T extends Record<string, string>>(map: T): T {
  return new Proxy(map, {
    get(target, key) {
      const v = Reflect.get(target, key);
      return typeof v === "string" ? t(v) : v;
    },
  });
}
