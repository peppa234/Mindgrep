package main

import (
	"net/http"
	"net/url"
	"sync"
	"time"

	"golang.org/x/net/html"
)

// BrokenLink is a link that returned an error status or could not be fetched at all.
type BrokenLink struct {
	URL    string
	Parent string
	Status int
}

type job struct {
	url    string
	parent string
	depth  int
}

// Crawler walks a site breadth-first with a fixed pool of worker goroutines.
type Crawler struct {
	client   *http.Client
	workers  int
	maxDepth int

	mu      sync.Mutex
	visited map[string]bool
	broken  []BrokenLink
}

func NewCrawler(workers, maxDepth int, timeout time.Duration) *Crawler {
	return &Crawler{
		client:   &http.Client{Timeout: timeout},
		workers:  workers,
		maxDepth: maxDepth,
		visited:  make(map[string]bool),
	}
}

// Run crawls from start and returns every broken link found. Jobs flow through a channel
// consumed by a worker pool; a WaitGroup counts outstanding jobs so we know when to stop.
func (c *Crawler) Run(start string) []BrokenLink {
	jobs := make(chan job, 1024)
	var pending sync.WaitGroup

	enqueue := func(j job) {
		c.mu.Lock()
		defer c.mu.Unlock()
		if c.visited[j.url] || j.depth > c.maxDepth {
			return
		}
		c.visited[j.url] = true
		pending.Add(1)
		jobs <- j
	}

	for i := 0; i < c.workers; i++ {
		go func() {
			for j := range jobs {
				for _, link := range c.fetch(j) {
					enqueue(job{url: link, parent: j.url, depth: j.depth + 1})
				}
				pending.Done()
			}
		}()
	}

	enqueue(job{url: start, depth: 0})
	pending.Wait()
	close(jobs)
	return c.broken
}

// fetch requests one page, records it if broken, and returns the same-host links on it.
func (c *Crawler) fetch(j job) []string {
	resp, err := c.client.Get(j.url)
	if err != nil {
		c.record(BrokenLink{URL: j.url, Parent: j.parent, Status: 0})
		return nil
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		c.record(BrokenLink{URL: j.url, Parent: j.parent, Status: resp.StatusCode})
		return nil
	}
	return extractLinks(j.url, resp)
}

func (c *Crawler) record(link BrokenLink) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.broken = append(c.broken, link)
}

// extractLinks parses the HTML body and resolves every <a href> against the page URL,
// keeping only links on the same host.
func extractLinks(pageURL string, resp *http.Response) []string {
	base, err := url.Parse(pageURL)
	if err != nil {
		return nil
	}
	doc, err := html.Parse(resp.Body)
	if err != nil {
		return nil
	}
	var links []string
	var walk func(*html.Node)
	walk = func(n *html.Node) {
		if n.Type == html.ElementNode && n.Data == "a" {
			for _, attr := range n.Attr {
				if attr.Key != "href" {
					continue
				}
				ref, err := url.Parse(attr.Val)
				if err != nil {
					continue
				}
				resolved := base.ResolveReference(ref)
				if resolved.Host == base.Host {
					resolved.Fragment = ""
					links = append(links, resolved.String())
				}
			}
		}
		for child := n.FirstChild; child != nil; child = child.NextSibling {
			walk(child)
		}
	}
	walk(doc)
	return links
}
