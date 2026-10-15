import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

// Matches CJK characters: UI text must come from the i18n dictionaries (CLAUDE.md hard rule 4).
const CJK = "/[\u3400-\u9fff\uff00-\uffef]/";

export default tseslint.config(
  {
    ignores: [
      "dist",
      "node_modules",
      "src/legacy/**", // upstream Hermes UI, removed after M2
    ],
  },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.strict],
    languageOptions: { ecmaVersion: 2023, globals: { ...globals.browser, ...globals.node } },
    plugins: { "react-hooks": reactHooks, "react-refresh": reactRefresh },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "no-restricted-syntax": [
        "error",
        {
          selector: `JSXText[value=${CJK}]`,
          message: "Hard-coded UI text: use t('…') from the i18n dictionaries.",
        },
        {
          selector: `JSXAttribute > Literal[value=${CJK}]`,
          message: "Hard-coded UI text: use t('…') from the i18n dictionaries.",
        },
      ],
    },
  },
  {
    files: ["src/components/ui/**/*.tsx"],
    rules: { "react-refresh/only-export-components": "off" },
  },
);
