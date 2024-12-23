from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, CreateView, UpdateView, View
from .models import Task, Sprint, Retrospective
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from .forms import UserRegistrationForm
from django.db.models import Count

class SprintMixin:
    def get_current_sprint(self, user):
        today = timezone.now().date()
        sprint = Sprint.objects.filter(
            user=user,
            start_date__lte=today,
            end_date__gte=today,
            status='active'
        ).first()
        
        if not sprint:
            # Create a new sprint starting from the most recent Monday
            monday = today - timedelta(days=today.weekday())
            sprint = Sprint.objects.create(
                user=user,
                start_date=monday,
                end_date=monday + timedelta(days=6),
                status='active'
            )
        
        return sprint

def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, 'Registration successful. Please login.')
            return redirect('login')
    else:
        form = UserRegistrationForm()
    return render(request, 'registration/register.html', {'form': form})

@login_required
def landing_page(request):
    if request.method == 'POST':
        title = request.POST.get('task')
        if title:
            Task.objects.create(
                title=title,
                status='inbox',
                user=request.user,
                cost=None,  # These will be set during processing
                benefit=None
            )
            messages.success(request, 'Task added successfully!')
        return redirect('landing')
    return render(request, 'tasks/landing.html')

class ProcessInboxView(LoginRequiredMixin, ListView):
    model = Task
    template_name = 'tasks/process_inbox.html'
    context_object_name = 'tasks'

    def get_queryset(self):
        return Task.objects.filter(status='inbox', user=self.request.user)

    def post(self, request, *args, **kwargs):
        task_id = request.POST.get('task_id')
        action = request.POST.get('action')
        
        if task_id and action:
            task = get_object_or_404(Task, id=task_id, user=request.user)
            
            if action == 'make_project' or action == 'backlog':
                # Get form data
                scope = request.POST.get('scope', '').strip()
                cost = request.POST.get('cost')
                benefit = request.POST.get('benefit')
                category = request.POST.get('category')
                estimated_time = request.POST.get('estimated_time')
                time_unit = request.POST.get('time_unit')
                
                if not category:
                    messages.error(request, 'Category is required')
                    return redirect('process_inbox')
                
                # Update task
                task.status = 'backlog'
                task.scope = scope
                task.category = category
                
                try:
                    task.estimated_time = int(estimated_time) if estimated_time else None
                    task.time_unit = time_unit if estimated_time else None
                    task.cost = int(cost) if cost else None
                    task.benefit = int(benefit) if benefit else None
                except ValueError:
                    messages.error(request, 'Invalid number format')
                    return redirect('process_inbox')
                
                # Set project flag if applicable
                if action == 'make_project':
                    task.is_project = True
                    msg = f'Project "{task.title}" created'
                else:
                    msg = f'Task "{task.title}" moved to backlog'
                
                task.save()
                messages.success(request, msg)
                
            elif action == 'done':
                task.status = 'done'
                task.save()
                messages.success(request, f'Task "{task.title}" marked as done.')
                
            elif action == 'delete':
                task.status = 'deleted'
                task.save()
                messages.success(request, f'Task "{task.title}" deleted.')
        
        return redirect('process_inbox')

class BacklogView(LoginRequiredMixin, SprintMixin, ListView):
    model = Task
    template_name = 'tasks/backlog.html'
    context_object_name = 'tasks'

    def get_queryset(self):
        # Only get top-level tasks (not subtasks)
        queryset = Task.objects.filter(
            status='backlog',
            user=self.request.user,
            parent_project__isnull=True  # Only get tasks that aren't subtasks
        ).prefetch_related('subtasks')  # Efficiently load subtasks
        return sorted(queryset, key=lambda t: t.priority_score(), reverse=True)

    def post(self, request, *args, **kwargs):
        action = request.POST.get('action')
        task_id = request.POST.get('task_id')
        
        if task_id and action:
            task = get_object_or_404(Task, id=task_id, user=request.user)
            
            if action == 'add_to_sprint':
                # Prevent adding projects to sprint
                if task.is_project:
                    messages.error(request, 'Projects cannot be added to sprint directly. Please add individual subtasks.')
                    return redirect('backlog')
                
                sprint = self.get_current_sprint(request.user)
                task.sprint = sprint
                task.save()
                messages.success(request, f'Added "{task.title}" to current sprint')
            
            elif action == 'add_subtask':
                parent_id = request.POST.get('parent_id')
                if parent_id:
                    try:
                        parent_task = Task.objects.get(
                            id=parent_id, 
                            user=request.user, 
                            is_project=True
                        )
                        
                        title = request.POST.get('title')
                        description = request.POST.get('description', '').strip()
                        
                        if title:
                            # Create subtask with minimal fields
                            subtask = Task.objects.create(
                                title=title,
                                scope=description,  # Using scope instead of description
                                status='backlog',
                                user=request.user,
                                parent_project=parent_task,
                                is_project=False  # Ensure it's not marked as a project
                            )
                            messages.success(request, f'Subtask "{title}" added to project "{parent_task.title}"')
                        else:
                            messages.error(request, 'Subtask title is required')
                    except Task.DoesNotExist:
                        messages.error(request, 'Invalid project selected')
                else:
                    messages.error(request, 'No project selected for subtask')
            
            elif action == 'update':
                # Get form data
                description = request.POST.get('description', '').strip()
                cost = request.POST.get('cost')
                benefit = request.POST.get('benefit')
                estimated_time = request.POST.get('estimated_time')
                
                # Update task
                task.description = description
                
                # Convert and validate cost
                try:
                    task.cost = int(cost) if cost else None
                except ValueError:
                    task.cost = None
                
                # Convert and validate benefit
                try:
                    task.benefit = int(benefit) if benefit else None
                except ValueError:
                    task.benefit = None
                
                # Convert and validate estimated time
                try:
                    task.estimated_time = int(estimated_time) if estimated_time else None
                except ValueError:
                    task.estimated_time = None
                
                task.save()
                messages.success(request, f'Task "{task.title}" has been updated.')
            
            elif action == 'done':
                # Check if it's a project and has incomplete subtasks
                if task.is_project and task.subtasks.exclude(status='done').exists():
                    messages.error(
                        request,
                        'Cannot complete project until all subtasks are done.'
                    )
                else:
                    task.status = 'done'
                    task.save()
                    messages.success(
                        request,
                        f'{"Project" if task.is_project else "Task"} "{task.title}" marked as complete.'
                    )
        
        return redirect('backlog')

class HistoryView(LoginRequiredMixin, ListView):
    model = Task
    template_name = 'tasks/history.html'
    context_object_name = 'tasks'

    def get_queryset(self):
        time_filter = self.request.GET.get('filter', 'all')
        # Only get tasks with completed_date
        queryset = Task.objects.filter(
            status='done',
            user=self.request.user,
            completed_date__isnull=False
        )

        if time_filter == 'today':
            queryset = queryset.filter(
                completed_date__date=timezone.now().date()
            )
        elif time_filter == 'week':
            queryset = queryset.filter(
                completed_date__gte=timezone.now() - timedelta(days=7)
            )
        elif time_filter == 'month':
            queryset = queryset.filter(
                completed_date__gte=timezone.now() - timedelta(days=30)
            )

        return queryset.order_by('-completed_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tasks = self.get_queryset()

        # Prepare data for charts
        tasks_data = []
        completion_dates = {}

        for task in tasks:
            if task.completed_date:  # Extra safety check
                # Data for scatter plot
                tasks_data.append({
                    'title': task.title,
                    'cost': task.cost or 0,
                    'benefit': task.benefit or 0,
                    'completed_date': task.completed_date.strftime('%Y-%m-%d')
                })

                # Count completions by date
                date_str = task.completed_date.strftime('%Y-%m-d')
                completion_dates[date_str] = completion_dates.get(date_str, 0) + 1

        # Sort dates and prepare chart data
        sorted_dates = sorted(completion_dates.keys())
        completion_counts = [completion_dates[date] for date in sorted_dates]

        context['tasks_json'] = {
            'tasks': tasks_data,
            'dates': sorted_dates,
            'completion_counts': completion_counts
        }
        
        return context

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            context = self.get_context_data(object_list=self.get_queryset())
            html = render_to_string(
                template_name=self.template_name,
                context=context,
                request=request
            )
            return HttpResponse(html)
            
        return response

class RetrospectiveView(LoginRequiredMixin, SprintMixin, View):
    template_name = 'tasks/retrospective.html'

    def get_sprint_analytics(self, sprint):
        sprint_tasks = Task.objects.filter(
            user=self.request.user,
            sprint=sprint
        )
        
        total_tasks = sprint_tasks.count()
        completed_tasks = sprint_tasks.filter(status='done').count()
        completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

        # Category distribution - handle None categories
        category_counts = sprint_tasks.filter(status='done').exclude(
            category__isnull=True
        ).values('category').annotate(count=Count('id'))
        
        # Get category choices dictionary
        category_choices = dict(Task.CATEGORY_CHOICES)
        
        # Create category data, safely handling categories
        category_data = {
            'labels': [],
            'values': []
        }
        
        for cat in category_counts:
            if cat['category'] in category_choices:
                category_data['labels'].append(category_choices[cat['category']])
                category_data['values'].append(cat['count'])

        # Time investment - handle None categories
        time_data = {
            'labels': [label for value, label in Task.CATEGORY_CHOICES],
            'values': []
        }
        
        for cat_value, _ in Task.CATEGORY_CHOICES:
            total_time = sum(
                t.estimated_time or 0 
                for t in sprint_tasks.filter(
                    category=cat_value,
                    status='done'
                )
            )
            time_data['values'].append(total_time)

        return {
            'completion_rate': round(completion_rate, 1),
            'completed_tasks': completed_tasks,
            'total_tasks': total_tasks,
            'category_data': category_data,
            'time_data': time_data
        }

    def get(self, request):
        sprint = self.get_current_sprint(request.user)
        if not sprint:
            messages.warning(request, 'No active sprint found.')
            return redirect('sprint')
        
        context = {
            'sprint': sprint,
            'is_sunday': timezone.now().date().weekday() == 6,
            **self.get_sprint_analytics(sprint)  # Spread the analytics data into context
        }
        
        # Get retrospective if it exists
        retrospective = Retrospective.objects.filter(sprint=sprint).first()
        if retrospective:
            context['retrospective'] = retrospective
        
        return render(request, self.template_name, context)

    def post(self, request):
        action = request.POST.get('action')
        sprint = self.get_current_sprint(request.user)
        
        if not sprint:
            messages.error(request, 'No active sprint found.')
            return redirect('sprint')
        
        if action == 'save_retrospective':
            retrospective, created = Retrospective.objects.get_or_create(
                sprint=sprint,
                user=request.user
            )
            
            # Update retrospective fields
            retrospective.went_well = request.POST.get('went_well', '')
            retrospective.could_improve = request.POST.get('could_improve', '')
            retrospective.lessons_learned = request.POST.get('lessons_learned', '')
            retrospective.next_sprint_goals = request.POST.get('next_sprint_goals', '')
            retrospective.action_items = request.POST.get('action_items', '')
            retrospective.save()
            
            messages.success(request, 'Retrospective saved successfully.')
            
        elif action == 'complete_sprint':
            if not Retrospective.objects.filter(sprint=sprint).exists():
                messages.error(request, 'Please complete the retrospective first.')
                return redirect('retrospective')
            
            # Complete current sprint
            sprint.status = 'completed'
            sprint.save()
            
            # Create next sprint
            next_sprint_start = sprint.end_date + timedelta(days=1)
            next_sprint_end = next_sprint_start + timedelta(days=6)
            
            Sprint.objects.create(
                start_date=next_sprint_start,
                end_date=next_sprint_end,
                status='active',
                user=request.user
            )
            
            messages.success(request, 'Sprint completed and new sprint created.')
            return redirect('sprint')
        
        return redirect('retrospective')

class SprintView(LoginRequiredMixin, SprintMixin, View):
    template_name = 'tasks/sprint.html'

    def get(self, request):
        sprint = self.get_current_sprint(request.user)
        is_sunday = timezone.now().date().weekday() == 6
        
        context = {
            'sprint': sprint,
            'is_sunday': is_sunday,
            'todo_tasks': Task.objects.filter(
                sprint=sprint,
                user=request.user,
                status='backlog'
            ),
            'in_progress_tasks': Task.objects.filter(
                sprint=sprint,
                user=request.user,
                status='in_progress'
            ),
            'done_tasks': Task.objects.filter(
                sprint=sprint,
                user=request.user,
                status='done'
            )
        }
        
        return render(request, self.template_name, context)

    def post(self, request):
        action = request.POST.get('action')
        task_id = request.POST.get('task_id')
        
        if task_id and action:
            task = get_object_or_404(Task, id=task_id, user=request.user)
            sprint = self.get_current_sprint(request.user)
            
            if action == 'start':
                task.status = 'in_progress'
                task.sprint = sprint
                task.save()
                messages.success(request, f'Started working on "{task.title}"')
                
            elif action == 'complete':
                task.status = 'done'
                task.completed_date = timezone.now()
                task.save()
                messages.success(request, f'Completed "{task.title}"')
                
                # Check if this task is a subtask and update parent project if needed
                if task.parent_project:
                    parent = task.parent_project
                    if not parent.has_incomplete_subtasks():
                        parent.status = 'done'
                        parent.completed_date = timezone.now()
                        parent.save()
                        messages.success(request, f'Project "{parent.title}" completed as all subtasks are done!')
        
        return redirect('sprint')
