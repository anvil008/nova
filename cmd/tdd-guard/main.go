package main

import (
	"os"

	"github.com/anvil008/workcell/guard"
)

func main() {
	os.Exit(guard.Run(guard.Options{Stdin: os.Stdin, Stdout: os.Stdout, Stderr: os.Stderr}, os.Args[1:]))
}
