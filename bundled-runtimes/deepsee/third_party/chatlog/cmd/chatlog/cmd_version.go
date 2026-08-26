package chatlog

import (
	"fmt"

	"github.com/sjzar/chatlog/pkg/version"

	"github.com/spf13/cobra"
)

func init() {
	rootCmd.AddCommand(versionCmd)
	versionCmd.Flags().BoolVarP(&versionM, "module", "m", false, "module version information")
}

var versionM bool
var versionCmd = &cobra.Command{
	Use:   "version [-m]",
	Short: "Show the version of chatlog",
	Run: func(cmd *cobra.Command, args []string) {
		if versionM {
			fmt.Println(version.GetMore(true))
		} else {
			fmt.Printf("chatlog %s\n", version.GetMore(false))
		}
	},
}
