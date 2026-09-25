package main

import (
	"flag"
	"fmt"
	"os"
	"time"
)

func main() {
	start := flag.String("url", "", "page to start crawling from")
	workers := flag.Int("workers", 8, "number of concurrent fetchers")
	depth := flag.Int("depth", 3, "maximum link depth to follow")
	timeout := flag.Duration("timeout", 10*time.Second, "per-request timeout")
	flag.Parse()

	if *start == "" {
		fmt.Fprintln(os.Stderr, "usage: link-checker -url https://example.com")
		os.Exit(2)
	}

	crawler := NewCrawler(*workers, *depth, *timeout)
	broken := crawler.Run(*start)
	for _, link := range broken {
		fmt.Printf("%d\t%s\t(found on %s)\n", link.Status, link.URL, link.Parent)
	}
	if len(broken) > 0 {
		os.Exit(1)
	}
}
