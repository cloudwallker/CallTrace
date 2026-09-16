import { leaf } from './service';
export async function main(provider: { missing(): void }) {
  if (await leaf()) {
    for (let i = 0; i < 2; i++) leaf();
  } else {
    provider.missing();
  }
  main(provider);
}
