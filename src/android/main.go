package main

import (
	"fmt"
	"time"
)

func main() {
	fmt.Printf("[%s] Started SMS Gateway Proxy\n", time.Now().Format("2006-01-02 15:04:05"))

	// Emit a log message every 2 seconds
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()

	counter := 0
	for range ticker.C {
		counter++
		fmt.Printf("[%s] Log message #%d from smsgap\n", time.Now().Format("2006-01-02 15:04:05"), counter)
	}
}
