"""
滚轮事件过滤器
解决Qt控件（如QComboBox、QSpinBox等）捕获滚轮事件导致页面无法滚动的问题
"""

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox, QSlider


class NoWheelComboBox(QComboBox):
    """禁用滚轮事件的下拉框"""
    
    def wheelEvent(self, event):
        """完全忽略滚轮事件"""
        event.ignore()


class WheelEventFilter(QObject):
    """
    滚轮事件过滤器
    阻止未获得焦点的控件响应滚轮事件，从而让滚轮事件传递给父控件（滚动区域）
    """
    
    def eventFilter(self, obj, event):
        """
        过滤事件
        完全阻止下拉菜单响应滚轮事件
        """
        if event.type() == QEvent.Type.Wheel:
            # 检查是否是需要特殊处理的控件
            if isinstance(obj, (QComboBox, QSpinBox, QDoubleSpinBox, QSlider)):
                # 完全忽略滚轮事件，无论是否有焦点
                event.ignore()
                
                # 手动向上冒泡，确保 QScrollArea 等父容器能够接收到滚动事件
                from PyQt6.QtWidgets import QApplication
                parent = obj.parentWidget()
                while parent:
                    QApplication.sendEvent(parent, event)
                    if event.isAccepted():
                        break
                    parent = parent.parentWidget()
                
                return True
        
        # 继续正常处理其他事件
        return super().eventFilter(obj, event)


def install_wheel_filter(widget):
    """
    为指定控件及其所有子控件安装滚轮事件过滤器
    
    Args:
        widget: 需要安装过滤器的顶层控件
    """
    wheel_filter = WheelEventFilter(widget)
    
    # 递归为所有子控件安装过滤器
    def install_recursive(w):
        if isinstance(w, (QComboBox, QSpinBox, QDoubleSpinBox, QSlider)):
            w.installEventFilter(wheel_filter)
            # 禁用控件的焦点策略为滚轮焦点
            w.setFocusPolicy(w.focusPolicy() & ~0x0008)  # 移除 WheelFocus
        
        # 递归处理子控件
        for child in w.findChildren(QComboBox):
            child.installEventFilter(wheel_filter)
            child.setFocusPolicy(child.focusPolicy() & ~0x0008)
        
        for child in w.findChildren(QSpinBox):
            child.installEventFilter(wheel_filter)
            child.setFocusPolicy(child.focusPolicy() & ~0x0008)
        
        for child in w.findChildren(QDoubleSpinBox):
            child.installEventFilter(wheel_filter)
            child.setFocusPolicy(child.focusPolicy() & ~0x0008)

        for child in w.findChildren(QSlider):
            child.installEventFilter(wheel_filter)
            child.setFocusPolicy(child.focusPolicy() & ~0x0008)
    
    install_recursive(widget)
    return wheel_filter
