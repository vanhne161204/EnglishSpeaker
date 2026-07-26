module.exports = {
  root: true,
  parser: "@typescript-eslint/parser",
  parserOptions: { ecmaFeatures: { jsx: true } },
  plugins: ["@typescript-eslint"],
  extends: ["eslint:recommended", "plugin:@typescript-eslint/recommended"],
  env: { es2021: true, node: true },
  ignorePatterns: ["node_modules/", "babel.config.js", ".eslintrc.js"],
};
