// ArkTS sample exercising V1 + V2 decorators, lifecycle, build(), resources,
// provide/consume, storage bindings, watch, monitor, observedV2+trace, and
// cross-component UI composition.
import { TitleBar } from './TitleBar'
import { common } from '@kit.AbilityKit'

interface CheckRule {
  passMessage: string
  passValue: number
}

enum CheckState {
  NOT_START = 0,
  CHECKING = 1,
  DONE = 2,
}

@ObservedV2
class CheckBean {
  @Trace state: CheckState = CheckState.NOT_START
  @Trace progress: number = 0
  iconID: Resource = $r("app.media.icon")
}

@Entry({
  routeName: "EnvCheckPage"
})
@ComponentV2
export struct EnvCheckPage {
  @Local checkState: CheckState = CheckState.NOT_START
  @Local model: TitleBar.Model = new TitleBar.Model()
  @State oldFashionedState: string = "hello"
  @Param requiredProp: string = ""
  @Event onChange: (v: number) => void = () => {}
  @Provider('sharedKey') shared: number = 0
  @Computed get total(): number {
    return this.oldFashionedState.length
  }
  @Monitor('checkState', 'model.titleName')
  onStateChange(): void {
    this.reset()
  }
  @Watch('onCountChange') count: number = 0
  @StorageLink('globalUser') user: string = ""
  @LocalStorageProp('sessionId') sid: string = ""
  private storageId: number = -1

  aboutToAppear(): void {
    this.startCheck()
  }

  onPageShow(): void {
    this.reset()
  }

  onCountChange(): void {
    console.info("count changed")
  }

  build() {
    NavDestination() {
      Column() {
        TitleBar({ model: this.model }).height(50)
        Scroll() {
          Column() {
            List() {
              ForEach([1, 2, 3], (item: number) => {
                ListItem() {
                  Text(`Item ${item}`)
                    .fontSize(16)
                    .fontColor($r('app.color.color_text'))
                }
              })
            }
          }
        }
        Button($r('app.string.submit'))
          .backgroundColor(Color.Blue)
          .onClick(() => this.reset())
      }
    }
  }

  private startCheck(): void {
    this.checkState = CheckState.CHECKING
  }

  private reset(): void {
    this.checkState = CheckState.NOT_START
  }
}

@Component
struct LegacyPage {
  @Prop title: string = ""
  @Link shared: number
  @Consume('sharedKey') injected: number = 0

  build() {
    Text(this.title)
  }
}
