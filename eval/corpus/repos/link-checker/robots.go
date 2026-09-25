package main

import (
	"bufio"
	"io"
	"strings"
)

// RobotsRules holds the Disallow prefixes that apply to our user agent.
type RobotsRules struct {
	disallow []string
}

// ParseRobots reads a robots.txt body and keeps the rules for "*" and for agent.
// Groups for other user agents are skipped.
func ParseRobots(body io.Reader, agent string) *RobotsRules {
	rules := &RobotsRules{}
	scanner := bufio.NewScanner(body)
	applies := false
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if i := strings.Index(line, "#"); i >= 0 {
			line = strings.TrimSpace(line[:i])
		}
		key, value, ok := strings.Cut(line, ":")
		if !ok {
			continue
		}
		key = strings.ToLower(strings.TrimSpace(key))
		value = strings.TrimSpace(value)
		switch key {
		case "user-agent":
			applies = value == "*" || strings.EqualFold(value, agent)
		case "disallow":
			if applies && value != "" {
				rules.disallow = append(rules.disallow, value)
			}
		}
	}
	return rules
}

// Allowed reports whether path may be crawled under these rules.
func (r *RobotsRules) Allowed(path string) bool {
	for _, prefix := range r.disallow {
		if strings.HasPrefix(path, prefix) {
			return false
		}
	}
	return true
}
