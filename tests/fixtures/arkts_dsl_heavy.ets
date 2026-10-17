// ArkUI DSL (trailing-closure component calls) is not valid TypeScript; with a
// nested @Builder the TypeScript grammar's error recovery drops the class.
@ComponentV2
struct HeavyPage {
  @Local isLoadFailed: boolean = false

  aboutToAppear(): void {
    this.isLoadFailed = false
  }

  @Builder
  failedPage(onRetry: () => void, onClose: () => void) {
    Column() {
      Image($r("app.media.web_load_error_prompt"))
        .width(112)
        .height(112)
      Button('retry')
        .onClick(() => {
          onRetry()
        })
    }
    .height("100%")
    .width("100%")
  }

  build() {
    NavDestination() {
      Stack({ alignContent: Alignment.Bottom }) {
        this.failedPage(
          () => {
            try {
              this.isLoadFailed = false
            } catch (error) {
              this.isLoadFailed = true
            }
          },
          () => {
            this.isLoadFailed = true
          }
        )
      }
      .width('100%')
    }
    .height("100%")
  }
}
