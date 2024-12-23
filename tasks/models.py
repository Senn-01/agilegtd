from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.conf import settings

class Task(models.Model):
    STATUS_CHOICES = [
        ('inbox', 'Inbox'),
        ('backlog', 'Backlog'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('deleted', 'Deleted'),
    ]
    
    TIME_UNIT_CHOICES = [
        ('hours', 'Hours'),
        ('days', 'Days'),
        ('weeks', 'Weeks'),
    ]

    CATEGORY_CHOICES = [
        ('self_improvement', 'Self-Improvement'),
        ('leisure', 'Leisure'),
        ('personal_work', 'Personal Work'),
    ]

    title = models.CharField(max_length=200)
    scope = models.TextField(blank=True, help_text="Project scope and objectives")
    created_date = models.DateTimeField(default=timezone.now)
    modified_date = models.DateTimeField(auto_now=True)
    completed_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='inbox')
    
    # Task type and project management
    is_project = models.BooleanField(default=False)
    project_number = models.IntegerField(null=True, blank=True)
    parent_project = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='subtasks')
    
    # Priority metrics
    cost = models.IntegerField(null=True, blank=True, help_text="Effort required (0-10)")
    benefit = models.IntegerField(null=True, blank=True, help_text="Value gained (0-10)")
    
    # Time estimation
    estimated_time = models.IntegerField(null=True, blank=True)
    time_unit = models.CharField(max_length=10, choices=TIME_UNIT_CHOICES, default='hours', null=True, blank=True)
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tasks')
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        null=True,
        blank=True
    )
    sprint = models.ForeignKey(
        'Sprint',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tasks'
    )

    def save(self, *args, **kwargs):
        # Set project number for new projects
        if self.is_project and not self.project_number:
            last_project = Task.objects.filter(
                user=self.user,
                is_project=True
            ).order_by('-project_number').first()
            
            # Handle case where this is the first project
            if last_project and last_project.project_number:
                self.project_number = last_project.project_number + 1
            else:
                self.project_number = 1
            
        # Set completed date when status changes to done
        if self.status == 'done' and not self.completed_date:
            self.completed_date = timezone.now()
            
        super().save(*args, **kwargs)

    def get_time_estimate_display(self):
        """Return formatted time estimate."""
        if self.estimated_time and self.time_unit:
            return f"{self.estimated_time} {self.time_unit}"
        return "Not set"

    def __str__(self):
        return self.title

    def has_incomplete_subtasks(self):
        """Check if project has any incomplete subtasks."""
        if not self.is_project:
            return False
        return self.subtasks.exclude(status='done').exists()

    def can_be_added_to_sprint(self):
        """Determine if a task can be added to sprint."""
        return not self.is_project

    def complete(self):
        """Complete a task and handle project completion logic."""
        self.status = 'done'
        self.completed_date = timezone.now()
        self.save()
        
        # If this is a subtask, check if parent project should be completed
        if self.parent_project and not self.parent_project.has_incomplete_subtasks():
            self.parent_project.complete()

    def subtask_progress(self):
        """Return progress of subtasks as (completed, total)."""
        if not self.is_project:
            return (0, 0)
        total = self.subtasks.count()
        completed = self.subtasks.filter(status='done').count()
        return (completed, total)

    def priority_score(self):
        """Calculate priority score based on cost and benefit."""
        if self.cost is None or self.benefit is None:
            return 0
        return (self.benefit * 10) / (self.cost + 1)

    class Meta:
        ordering = ['-created_date']

class Sprint(models.Model):
    STATUS_CHOICES = [
        ('planned', 'Planned'),
        ('active', 'Active'),
        ('completed', 'Completed'),
    ]
    
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    def is_current(self):
        today = timezone.now().date()
        return self.start_date <= today <= self.end_date

class Retrospective(models.Model):
    sprint = models.OneToOneField(Sprint, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    completed_date = models.DateTimeField(auto_now_add=True)
    
    # Reflection
    went_well = models.TextField(blank=True)
    could_improve = models.TextField(blank=True)
    lessons_learned = models.TextField(blank=True)
    
    # Planning
    next_sprint_goals = models.TextField(blank=True)
    action_items = models.TextField(blank=True)
