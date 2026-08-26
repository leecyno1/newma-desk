package menu

import (
	"fmt"
	"sort"

	"github.com/sjzar/chatlog/internal/ui/style"

	"github.com/gdamore/tcell/v2"
	"github.com/rivo/tview"
)

const (
	// DialogPadding dialog inner paddign.
	DialogPadding = 3

	// DialogFormHeight dialog "Enter"/"Cancel" form height.
	DialogHelpHeight = 1

	// DialogMinWidth dialog min width.
	DialogMinWidth = 40

	// TableHeightOffset table height offset for border.
	TableHeightOffset = 3

	cmdWidthOffset = 6
)

type SubMenu struct {
	*tview.Box
	title         string
	layout        *tview.Flex
	table         *tview.Table
	width         int
	height        int
	items         []*Item
	cancelHandler func()
}

func NewSubMenu(title string) *SubMenu {
	subMenu := &SubMenu{
		Box:    tview.NewBox(),
		title:  title,
		items:  make([]*Item, 0),
		layout: tview.NewFlex(),
		table:  tview.NewTable(),
	}

	subMenu.table.SetBorders(false)
	subMenu.table.SetSelectable(true, false)
	subMenu.table.SetBorderColor(style.DialogBorderColor)
	subMenu.table.SetBackgroundColor(style.DialogBgColor)
	subMenu.table.SetTitleColor(style.DialogFgColor)
	subMenu.table.SetFixed(1, 1)

	subMenu.table.Select(1, 0).SetSelectedFunc(func(row, column int) {
		if row == 0 {
			return // 忽略表头
		}

		item := subMenu.items[row-1]
		if item.Selected != nil {
			item.Selected(item)
		}
	})

	subMenu.setTableHeader()

	// 帮助信息
	helpText := tview.NewTextView()
	helpText.SetDynamicColors(true)
	helpText.SetTextAlign(tview.AlignCenter)
	helpText.SetTextColor(style.DialogFgColor)
	helpText.SetBackgroundColor(style.DialogBgColor)
	fmt.Fprintf(helpText,
		"[%s::b]↑/↓[%s::b]: 导航  [%s::b]Enter[%s::b]: 选择  [%s::b]ESC[%s::b]: 返回",
		style.GetColorHex(style.MenuBgColor), style.GetColorHex(style.PageHeaderFgColor),
		style.GetColorHex(style.MenuBgColor), style.GetColorHex(style.PageHeaderFgColor),
		style.GetColorHex(style.MenuBgColor), style.GetColorHex(style.PageHeaderFgColor),
	)

	// 布局
	tableLayout := tview.NewFlex().SetDirection(tview.FlexColumn)
	tableLayout.AddItem(EmptyBoxSpace(style.DialogBgColor), 1, 0, true)
	tableLayout.AddItem(subMenu.table, 0, 1, true)
	tableLayout.AddItem(EmptyBoxSpace(style.DialogBgColor), 1, 0, true)

	subMenu.layout.SetDirection(tview.FlexRow)
	subMenu.layout.SetTitle(fmt.Sprintf("[::b]%s", subMenu.title))
	subMenu.layout.SetTitleColor(style.DialogFgColor)
	subMenu.layout.SetTitleAlign(tview.AlignCenter)
	subMenu.layout.AddItem(tableLayout, 0, 1, true)
	subMenu.layout.AddItem(helpText, DialogHelpHeight, 0, true)
	subMenu.layout.SetBorder(true)
	subMenu.layout.SetBorderColor(style.DialogBorderColor)
	subMenu.layout.SetBackgroundColor(style.DialogBgColor)

	return subMenu
}

func (m *SubMenu) setTableHeader() {
	m.table.SetCell(0, 0, tview.NewTableCell(fmt.Sprintf("[%s::b]%s", style.GetColorHex(style.TableHeaderFgColor), "命令")).
		SetExpansion(1).
		SetBackgroundColor(style.TableHeaderBgColor).
		SetTextColor(style.TableHeaderFgColor).
		SetAlign(tview.AlignLeft).
		SetSelectable(false))

	m.table.SetCell(0, 1, tview.NewTableCell(fmt.Sprintf("[%s::b]%s", style.GetColorHex(style.TableHeaderFgColor), "说明")).
		SetExpansion(1).
		SetBackgroundColor(style.TableHeaderBgColor).
		SetTextColor(style.TableHeaderFgColor).
		SetAlign(tview.AlignLeft).
		SetSelectable(false))
}

func (m *SubMenu) AddItem(item *Item) {
	m.items = append(m.items, item)
	sort.Sort(SortItems(m.items))
	m.refresh()
}

func (m *SubMenu) SetItems(items []*Item) {
	m.items = items
	m.refresh()
}

func (m *SubMenu) SetCancelFunc(handler func()) *SubMenu {
	m.cancelHandler = handler
	return m
}

func (m *SubMenu) refresh() {
	m.table.Clear()
	m.setTableHeader()

	col1Width := 0
	col2Width := 0

	row := 1
	for _, item := range m.items {
		if item.Hidden {
			continue
		}
		m.table.SetCell(row, 0, tview.NewTableCell(item.Name).
			SetTextColor(style.DialogFgColor).
			SetBackgroundColor(style.DialogBgColor).
			SetReference(item).
			SetAlign(tview.AlignLeft))
		m.table.SetCell(row, 1, tview.NewTableCell(item.Description).
			SetTextColor(style.DialogFgColor).
			SetBackgroundColor(style.DialogBgColor).
			SetReference(item).
			SetAlign(tview.AlignLeft))
		if len(item.Name) > col1Width {
			col1Width = len(item.Name)
		}
		if len(item.Description) > col2Width {
			col2Width = len(item.Description)
		}
		row++
	}

	m.width = col1Width + col2Width + 2 + cmdWidthOffset
	m.height = len(m.items) + TableHeightOffset + DialogHelpHeight + 1

}

func (m *SubMenu) Draw(screen tcell.Screen) {
	m.refresh()

	m.Box.DrawForSubclass(screen, m)
	m.layout.Draw(screen)
}

func (m *SubMenu) SetRect(x, y, width, height int) {
	ws := (width - m.width) / 2
	hs := ((height - m.height) / 2)
	dy := y + hs
	bWidth := m.width

	if m.width > width {
		ws = 0
		bWidth = width - 1
	}

	bHeight := m.height

	if m.height >= height {
		dy = y + 1
		bHeight = height - 1
	}

	m.Box.SetRect(x+ws, dy, bWidth, bHeight)

	x, y, width, height = m.Box.GetInnerRect()

	m.layout.SetRect(x, y, width, height)
}

func (m *SubMenu) Focus(delegate func(p tview.Primitive)) {
	delegate(m.table)
}

// HasFocus returns whether or not this primitive has focus
func (m *SubMenu) HasFocus() bool {
	// Check if the active menu has focus
	return m.table.HasFocus()
}

func (m *SubMenu) InputHandler() func(event *tcell.EventKey, setFocus func(p tview.Primitive)) {
	return m.WrapInputHandler(func(event *tcell.EventKey, setFocus func(p tview.Primitive)) {

		if event.Key() == tcell.KeyEscape && m.cancelHandler != nil {
			m.cancelHandler()
			return
		}

		// 将事件传递给表格
		if handler := m.table.InputHandler(); handler != nil {
			handler(event, setFocus)
		}
	})
}

func EmptyBoxSpace(bgColor tcell.Color) *tview.Box {
	box := tview.NewBox()
	box.SetBackgroundColor(bgColor)
	box.SetBorder(false)

	return box
}
