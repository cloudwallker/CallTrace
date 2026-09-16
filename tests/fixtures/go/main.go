package demo

import svc "example.test/fixture/service"

type Provider interface { Missing() }

func main(provider Provider) {
    if svc.Leaf() {
        for i := 0; i < 2; i++ { svc.Leaf() }
    } else {
        provider.Missing()
    }
    go svc.Leaf()
    main(provider)
}
