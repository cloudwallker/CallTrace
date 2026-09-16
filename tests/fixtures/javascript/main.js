import { leaf } from './service.js';
export async function main(provider) {
  if (await leaf()) {
    for (let i = 0; i < 2; i++) leaf();
  } else {
    provider.missing();
  }
  main(provider);
}
