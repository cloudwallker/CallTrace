package demo;
class Main {
    static void main(Provider provider) {
        if (Service.leaf()) {
            for (int i = 0; i < 2; i++) Service.leaf();
        } else {
            provider.missing();
        }
        main(provider);
    }
}
interface Provider { void missing(); }
